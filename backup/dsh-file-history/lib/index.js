// dsh-file-history — Host half (static / composition plugin)
//
// 目的：让 harness 在「改文件之前」自动留一份原文快照，不再依赖模型自觉。
//
//  1. 监听 tools/pre-execute：凡是 write / edit 且目标文件已存在 → 先把原文复制到
//     ~/.dsh/file-history/<workspace>/<sig>/<0001> 再放行；目标不存在（新建）不占用空间。
//  2. 校验：快照必须真的成功，否则**拦截这次写入**（fail-closed），杜绝「备份失败但照样改坏」。
//  3. 模型侧只多一个 file_history 工具：list / show / restore / revert_turn，
//     正常工作时零 token 成本，出错时一次调用即可回退（含整轮回退）。
//  4. 保留策略：单文件条数上限、单工作区容量上限、超期清理；二进制/超大文件只记哈希不存内容。
//
// 设计取舍：pre-execute 不能改写 exec.arguments，所以这里不做「挡下写入再由插件代写」——
// 那会丢掉 harness 原生的 read-before-write 校验和展示层 diff 卡片。这里只做旁路快照 + 校验，
// 让原工具照常执行，模型侧的可见行为完全不变。

import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile, readdir, stat, rm, rename, appendFile, open } from 'node:fs/promises'
import { homedir, tmpdir } from 'node:os'
import path from 'node:path'

/** 设置命名空间（持久化在 ~/.dsh/settings.yaml 的 file-history 段）。 */
export const SETTINGS_NS = 'file-history'
/** 插件在日志与快照元数据里的标识。 */
export const PLUGIN = 'file-history'
/** 快照根目录。 */
export const HISTORY_DIR = path.join(homedir(), '.dsh', 'file-history')
/** 会话级快照日志（JSONL），供用户直接翻查，也方便事后审计。 */
export const SESSIONS_DIR = path.join(HISTORY_DIR, '_sessions')

const HASH_LEN = 16
const DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024
const DEFAULT_MAX_AGE_DAYS = 30
const DEFAULT_MAX_WORKSPACE_BYTES = 512 * 1024 * 1024
const DEFAULT_MAX_ENTRIES_PER_FILE = 50
const SWEEP_INTERVAL_MS = 60 * 60 * 1000
const DIFF_MAX_LINES = 400
const LCS_BUDGET = 1200

/** 会被拦截并快照的文件修改类工具名（真实名 + PTC 限定名两种形态都覆盖）。 */
const MUTATING_TOOLS = new Set(['write', 'edit'])

/** 设置 schema：全部有默认值，用户段落可覆盖。 */
export const fileHistorySettingsSchema = (s) => s.object({
  /** 总开关；关闭后不再快照，也不再拦截。 */
  enabled: s.boolean().default(true),
  /** 超过该字节数的文件只记哈希，不复制内容（避免备份区被大文件撑爆）。 */
  maxFileBytes: s.natural().default(DEFAULT_MAX_FILE_BYTES),
  /** 快照保留天数。 */
  maxAgeDays: s.natural().default(DEFAULT_MAX_AGE_DAYS),
  /** 单个工作区快照区容量上限（字节）。 */
  maxWorkspaceBytes: s.natural().default(DEFAULT_MAX_WORKSPACE_BYTES),
  /** 单个文件最多保留多少代快照。 */
  maxEntriesPerFile: s.natural().default(DEFAULT_MAX_ENTRIES_PER_FILE),
})

// ───────────────────────────── 小工具 ─────────────────────────────

function sha256(buf) {
  return createHash('sha256').update(buf).digest('hex')
}

function shortHash(text) {
  return sha256(Buffer.from(text, 'utf8')).slice(0, HASH_LEN)
}

/** 工作区标识：目录名 + 路径哈希，既好认又不撞车。 */
function workspaceIdentity(cwd) {
  if (!cwd) return { key: 'unknown', name: 'unknown', cwd: '' }
  const resolved = path.resolve(cwd)
  const base = path.basename(resolved) || resolved.replace(/[:\\/]+/g, '_')
  const safe = base.replace(/[^\w\u4e00-\u9fa5.@-]+/g, '_').slice(0, 40) || 'ws'
  return { key: `${safe}-${shortHash(resolved.toLowerCase())}`, name: base, cwd: resolved }
}

/** 文件签名目录：可读文件名 + 路径哈希。 */
function fileSignature(name, absPath) {
  const safe = (name || 'file').replace(/[^\w\u4e00-\u9fa5.@+-]+/g, '_').slice(0, 48) || 'file'
  return `${safe}-${shortHash(absPath.toLowerCase())}`
}

/** 把模型给的路径解析成绝对路径：绝对路径原样，相对路径按会话 cwd 解析。 */
function resolveTarget(target, cwd) {
  if (!target || typeof target !== 'string') return undefined
  if (path.isAbsolute(target)) return path.normalize(target)
  if (!cwd) return undefined
  return path.normalize(path.resolve(cwd, target))
}

function formatBytes(n) {
  if (!Number.isFinite(n)) return '?'
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

function iso(ms) {
  try {
    return new Date(ms).toISOString().replace('T', ' ').slice(0, 19)
  } catch {
    return ''
  }
}

function looksBinary(buf) {
  const end = Math.min(buf.length, 8192)
  for (let i = 0; i < end; i += 1) {
    if (buf[i] === 0) return true
  }
  return false
}

/** 原子写：同目录临时文件 + rename，避免半截文件。 */
async function atomicWrite(absPath, data) {
  const dir = path.dirname(absPath)
  await mkdir(dir, { recursive: true })
  const tmp = path.join(dir, `.${path.basename(absPath)}.fh-${process.pid}-${Date.now()}.tmp`)
  await writeFile(tmp, data)
  try {
    await rename(tmp, absPath)
  } catch (error) {
    await rm(tmp, { force: true }).catch(() => {})
    throw error
  }
}

/** 文件被写者短暂占用时重试（Windows 上 write 的 rename 与我们的读可能撞车）。 */
async function readWithRetry(absPath, attempts = 4) {
  let lastError
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await readFile(absPath)
    } catch (error) {
      lastError = error
      if (error && (error.code === 'ENOENT' || error.code === 'EISDIR' || error.code === 'EACCES')) throw error
      await new Promise((resolve) => setTimeout(resolve, 30 * (attempt + 1)))
    }
  }
  throw lastError
}

async function appendSessionLog(record) {
  try {
    await mkdir(SESSIONS_DIR, { recursive: true })
    await appendFile(path.join(SESSIONS_DIR, `${record.sessionId || 'unknown'}.jsonl`), `${JSON.stringify(record)}\n`, 'utf8')
  } catch {
    /* 日志失败绝不影响主流程 */
  }
}

function sanitizeId(id) {
  return String(id || '').replace(/[^\w.-]+/g, '_').slice(0, 64)
}

// ─────────────────────────── 快照元数据索引 ───────────────────────────

/** 读取某个工作区下全部快照元数据（倒序由调用方决定）。 */
async function loadWorkspaceEntries(wsKey) {
  const dir = path.join(HISTORY_DIR, wsKey)
  let sigs
  try {
    sigs = await readdir(dir, { withFileTypes: true })
  } catch {
    return []
  }
  const entries = []
  for (const sig of sigs) {
    if (!sig.isDirectory() || sig.name.startsWith('_')) continue
    const sigDir = path.join(dir, sig.name)
    let ids
    try {
      ids = await readdir(sigDir)
    } catch {
      continue
    }
    for (const id of ids) {
      if (!/^\d+$/.test(id)) continue
      const entryDir = path.join(sigDir, id)
      try {
        const meta = JSON.parse(await readFile(path.join(entryDir, 'meta.json'), 'utf8'))
        const stored = await stat(path.join(entryDir, 'content')).then(
          (s) => ({ stored: true, size: s.size }),
          () => ({ stored: false, size: 0 }),
        )
        entries.push({
          id,
          entryId: `${wsKey}/${sig.name}/${id}`,
          dir: entryDir,
          restorable: stored.stored,
          contentSize: stored.size,
          ...meta,
        })
      } catch {
        /* 残缺目录跳过 */
      }
    }
  }
  entries.sort(byNewest)
  return entries
}

/** 稳定排序键：时间优先，同毫秒按代数（目录序号）区分，避免同轮改动出现不确定顺序。 */
function byNewest(a, b) {
  const delta = (b.time || 0) - (a.time || 0)
  if (delta !== 0) return delta
  return Number(b.id || 0) - Number(a.id || 0)
}

/** 列出所有工作区的快照（按时间倒序）。 */
async function loadAllEntries(limit) {
  let workspaces
  try {
    workspaces = await readdir(HISTORY_DIR, { withFileTypes: true })
  } catch {
    return []
  }
  const all = []
  for (const ws of workspaces) {
    if (!ws.isDirectory() || ws.name.startsWith('_')) continue
    const entries = await loadWorkspaceEntries(ws.name)
    for (const entry of entries) all.push(entry)
    if (all.length > limit * 4) break
  }
  all.sort(byNewest)
  return all.slice(0, limit)
}

// ─────────────────────────── 保留策略 ───────────────────────────

async function dirSize(dir) {
  let total = 0
  let items
  try {
    items = await readdir(dir, { withFileTypes: true })
  } catch {
    return 0
  }
  for (const item of items) {
    const child = path.join(dir, item.name)
    if (item.isDirectory()) total += await dirSize(child)
    else {
      try {
        total += (await stat(child)).size
      } catch {
        /* 并发删除 */
      }
    }
  }
  return total
}

async function trimFileSignatures(wsKey, maxPerFile) {
  const dir = path.join(HISTORY_DIR, wsKey)
  let sigs
  try {
    sigs = await readdir(dir, { withFileTypes: true })
  } catch {
    return
  }
  for (const sig of sigs) {
    if (!sig.isDirectory()) continue
    const sigDir = path.join(dir, sig.name)
    let ids
    try {
      ids = (await readdir(sigDir)).filter((id) => /^\d+$/.test(id)).sort()
    } catch {
      continue
    }
    const excess = ids.length - maxPerFile
    if (excess > 0) await trimSignatureDir(sigDir, ids, maxPerFile)
  }
}

async function sweepWorkspace(wsKey, settings) {
  const dir = path.join(HISTORY_DIR, wsKey)
  const entries = await loadWorkspaceEntries(wsKey)
  const cutoff = Date.now() - settings.maxAgeDays * 24 * 60 * 60 * 1000
  for (const entry of entries) {
    if ((entry.time || 0) < cutoff) await rm(entry.dir, { recursive: true, force: true }).catch(() => {})
  }
  await trimFileSignatures(wsKey, settings.maxEntriesPerFile)
  let total = await dirSize(dir)
  if (total <= settings.maxWorkspaceBytes) return
  const remaining = (await loadWorkspaceEntries(wsKey)).sort((a, b) => (a.time || 0) - (b.time || 0))
  for (const entry of remaining) {
    if (total <= settings.maxWorkspaceBytes) break
    try {
      total -= await dirSize(entry.dir)
      await rm(entry.dir, { recursive: true, force: true })
    } catch {
      /* 忽略 */
    }
  }
}

// ─────────────────────────── 快照 ───────────────────────────

/** 只保留最新 keep 代（新的快照即将占用一代，故传 maxEntriesPerFile - 1）。 */
async function trimSignatureDir(sigDir, ids, keep) {
  if (ids.length <= keep) return
  for (const id of ids.slice(0, ids.length - keep)) {
    await rm(path.join(sigDir, id), { recursive: true, force: true }).catch(() => {})
  }
}

/**
 * 为一次即将发生的覆盖写入留快照。
 * @returns 成功返回条目信息；无需快照返回 undefined；失败抛错（调用方据此拦截写入）。
 */
async function snapshotBeforeWrite(exec, settings) {
  const args = exec.arguments && typeof exec.arguments === 'object' ? exec.arguments : {}
  const requested = typeof args.file_path === 'string' ? args.file_path : undefined
  const agent = exec.agent
  const header = agent && agent.session ? agent.session.header : undefined
  const cwd = header ? header.cwd : undefined
  const absPath = resolveTarget(requested, cwd)
  if (!absPath) return undefined

  // 目标不存在 → 新建文件，没有可保护的原内容。
  let st
  try {
    st = await stat(absPath)
  } catch {
    return undefined
  }
  if (!st.isFile() || st.size === 0) return undefined

  const workspace = workspaceIdentity(cwd)
  const sig = fileSignature(path.basename(absPath), absPath)
  const sigDir = path.join(HISTORY_DIR, workspace.key, sig)
  await mkdir(sigDir, { recursive: true })

  // 代数上限就地执行：每次快照都裁剪，不依赖小时级的 sweep（否则短时间内连改会留一堆）。
  const existing = (await readdir(sigDir).catch(() => [])).filter((id) => /^\d+$/.test(id)).sort((a, b) => Number(a) - Number(b))
  const seq = String(existing.reduce((max, id) => Math.max(max, Number(id)), 0) + 1).padStart(4, '0')
  await trimSignatureDir(sigDir, existing, settings.maxEntriesPerFile - 1)
  const entryDir = path.join(sigDir, seq)
  await mkdir(entryDir, { recursive: true })

  const tooLarge = st.size > settings.maxFileBytes
  let bytes
  if (!tooLarge) {
    try {
      bytes = await readWithRetry(absPath)
    } catch (error) {
      await rm(entryDir, { recursive: true, force: true }).catch(() => {})
      throw new Error(`无法读取原文件用于快照: ${error && error.message ? error.message : error}`)
    }
  }

  const binary = bytes ? looksBinary(bytes) : false
  const storeContent = Boolean(bytes) && !binary

  if (storeContent) {
    // 写盘期间原文件若已被改动（mtime/size 变化），这份快照就不再是「改前版本」，宁可丢弃也不能留错版。
    const after = await stat(absPath).catch(() => undefined)
    if (!after || after.mtimeMs !== st.mtimeMs || after.size !== st.size) {
      await rm(entryDir, { recursive: true, force: true }).catch(() => {})
      throw new Error('原文件在快照期间被并发修改，已放弃本次快照（写入未执行）')
    }
    await writeFile(path.join(entryDir, 'content'), bytes)
  }

  const fingerprint = bytes ? sha256(bytes) : shortHash(`${st.size}:${st.mtimeMs}`)
  const sessionId = header && header.id ? String(header.id) : ''
  const meta = {
    id: seq,
    time: Date.now(),
    ms: st.mtimeMs,
    originalPath: absPath,
    displayPath: requested || absPath,
    workspaceKey: workspace.key,
    workspaceName: workspace.name,
    workspaceCwd: workspace.cwd,
    size: st.size,
    hash: fingerprint,
    hashKind: bytes ? 'sha256' : 'size+mtime',
    tool: exec.name,
    stored: storeContent,
    binary,
    reason: storeContent ? '' : binary ? '二进制文件只记哈希' : `超过 ${formatBytes(settings.maxFileBytes)} 只记指纹`,
    callId: String(exec.callId || ''),
    sessionId,
    sessionTitle: header && header.title ? String(header.title).slice(0, 200) : '',
    sessionTurnId: String(exec.rootCallId || ''),
  }
  await writeFile(path.join(entryDir, 'meta.json'), `${JSON.stringify(meta, null, 2)}\n`, 'utf8')
  await appendSessionLog({ kind: 'snapshot', at: meta.time, ...meta, dir: entryDir })
  return meta
}

// ─────────────────────────── diff ───────────────────────────

function splitLines(text) {
  return text.length === 0 ? [] : text.split(/\r?\n/)
}

/** 行级 diff：先剥公共前后缀，再对中间段做 LCS，超预算则退化为整段替换。 */
function diffLines(oldLines, newLines) {
  let start = 0
  while (start < oldLines.length && start < newLines.length && oldLines[start] === newLines[start]) start += 1
  let endOld = oldLines.length
  let endNew = newLines.length
  while (endOld > start && endNew > start && oldLines[endOld - 1] === newLines[endNew - 1]) {
    endOld -= 1
    endNew -= 1
  }
  const a = oldLines.slice(start, endOld)
  const b = newLines.slice(start, endNew)
  const result = []
  for (let i = 0; i < start; i += 1) result.push(`  ${oldLines[i]}`)
  if (a.length * b.length > LCS_BUDGET * LCS_BUDGET) {
    for (const line of a) result.push(`- ${line}`)
    for (const line of b) result.push(`+ ${line}`)
  } else {
    const n = a.length
    const m = b.length
    const table = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1))
    for (let i = n - 1; i >= 0; i -= 1) {
      for (let j = m - 1; j >= 0; j -= 1) {
        table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1])
      }
    }
    let i = 0
    let j = 0
    while (i < n && j < m) {
      if (a[i] === b[j]) {
        result.push(`  ${a[i]}`)
        i += 1
        j += 1
      } else if (table[i + 1][j] >= table[i][j + 1]) {
        result.push(`- ${a[i]}`)
        i += 1
      } else {
        result.push(`+ ${b[j]}`)
        j += 1
      }
    }
    while (i < n) result.push(`- ${a[i]}`), (i += 1)
    while (j < m) result.push(`+ ${b[j]}`), (j += 1)
  }
  for (let k = endOld; k < oldLines.length; k += 1) result.push(`  ${oldLines[k]}`)
  return result
}

// ─────────────────────────── 工具实现 ───────────────────────────

function entriesToValue(entries) {
  return entries.map((entry) => ({
    entryId: entry.entryId,
    time: iso(entry.time),
    path: entry.originalPath,
    size: entry.size,
    restorable: Boolean(entry.restorable),
    note: entry.reason || '',
    tool: entry.tool || '',
  }))
}

async function readEntryContent(entry) {
  if (!entry.restorable) return undefined
  return readFile(path.join(entry.dir, 'content'))
}

async function handleList(args, exec, settings) {
  const limit = Math.max(1, Math.min(Number(args.limit) || 20, 100))
  const sessionId = exec.agent && exec.agent.session && exec.agent.session.header ? String(exec.agent.session.header.id) : ''
  let entries = await loadAllEntries(Math.max(limit * 3, 60))
  if (args.scope === 'session' && sessionId) entries = entries.filter((entry) => entry.sessionId === sessionId)
  if (typeof args.query === 'string' && args.query.trim()) {
    const needle = args.query.trim().toLowerCase()
    entries = entries.filter((entry) => String(entry.originalPath).toLowerCase().includes(needle))
  }
  const slice = entries.slice(0, limit)
  return {
    action: 'list',
    status: slice.length ? 'ok' : 'empty',
    message: slice.length
      ? `最近 ${slice.length} 条快照（保留 ${settings.maxAgeDays} 天 / 单文件 ${settings.maxEntriesPerFile} 代）`
      : '没有匹配的快照记录。只有「覆盖已存在文件」的 write/edit 才会留快照。',
    count: slice.length,
    entries: entriesToValue(slice),
  }
}

async function handleShow(args, exec) {
  const entries = await loadAllEntries(200)
  let entry
  if (args.entryId) entry = entries.find((candidate) => candidate.entryId === String(args.entryId))
  else {
    const abs = resolveTarget(String(args.path || ''), exec.agent && exec.agent.session ? exec.agent.session.header.cwd : undefined)
    if (!abs) return { action: 'show', status: 'error', message: '需要 path（相对会话工作区）或 entryId', count: 0, entries: [] }
    entry = entries.find((candidate) => candidate.originalPath === abs)
  }
  if (!entry) return { action: 'show', status: 'not_found', message: '没找到对应快照；可用 action=list 查看可用条目。', count: 0, entries: [] }
  const head = [
    `快照 ${entry.entryId}`,
    `原文件: ${entry.originalPath}`,
    `时间: ${iso(entry.time)}  大小: ${formatBytes(entry.size)}  工具: ${entry.tool}`,
  ]
  if (!entry.restorable) {
    head.push(`无内容副本（${entry.reason}），只能确认「改前状态」：sha256=${entry.hash}`)
    return { action: 'show', status: 'meta_only', message: head.join('\n'), count: 1, entries: entriesToValue([entry]) }
  }
  const beforeBytes = await readEntryContent(entry)
  let afterBytes
  try {
    afterBytes = await readFile(entry.originalPath)
  } catch {
    afterBytes = undefined
  }
  const before = splitLines(beforeBytes.toString('utf8'))
  if (!afterBytes) {
    head.push('当前文件已不存在（被删除或改名），下面是快照内容全文：')
    const body = before.slice(0, DIFF_MAX_LINES).map((line) => `  ${line}`)
    if (before.length > DIFF_MAX_LINES) body.push(`  …（还有 ${before.length - DIFF_MAX_LINES} 行，未显示）`)
    return { action: 'show', status: 'deleted', message: `${head.join('\n')}\n${body.join('\n')}`, count: 1, entries: entriesToValue([entry]) }
  }
  const after = splitLines(afterBytes.toString('utf8'))
  const diff = diffLines(before, after)
  const shown = diff.slice(0, DIFF_MAX_LINES)
  const tail = diff.length > shown.length ? `\n…（diff 共 ${diff.length} 行，已截断）` : ''
  const changed = diff.some((line) => line.startsWith('- ') || line.startsWith('+ '))
  head.push(`对比当前文件（- 改前 / + 现在）${changed ? '' : '：内容一致'}`)
  return { action: 'show', status: 'ok', message: `${head.join('\n')}\n${shown.join('\n')}${tail}`, count: 1, entries: entriesToValue([entry]) }
}

async function handleRestore(args, exec) {
  const entries = await loadAllEntries(200)
  let entry
  if (args.entryId) entry = entries.find((candidate) => candidate.entryId === String(args.entryId))
  else {
    const abs = resolveTarget(String(args.path || ''), exec.agent && exec.agent.session ? exec.agent.session.header.cwd : undefined)
    if (!abs) return { action: 'restore', status: 'error', message: '需要 path（相对会话工作区）或 entryId', count: 0, entries: [] }
    entry = entries.find((candidate) => candidate.originalPath === abs)
  }
  if (!entry) return { action: 'restore', status: 'not_found', message: '没找到对应快照，未做任何修改。', count: 0, entries: [] }
  if (!entry.restorable) {
    return { action: 'restore', status: 'meta_only', message: `该快照没有内容副本（${entry.reason}），无法还原。`, count: 0, entries: entriesToValue([entry]) }
  }
  const bytes = await readEntryContent(entry)
  if (!bytes) return { action: 'restore', status: 'error', message: '快照内容不可读或已过期。', count: 0, entries: [] }
  const target = resolveTarget(entry.displayPath, entry.workspaceCwd) || entry.originalPath
  await atomicWrite(target, bytes)
  await appendSessionLog({
    kind: 'restore',
    at: Date.now(),
    entryId: entry.entryId,
    target,
    sessionId: exec.agent && exec.agent.session && exec.agent.session.header ? String(exec.agent.session.header.id) : '',
  })
  return {
    action: 'restore',
    status: 'restored',
    message: `已还原 ${target} 到 ${iso(entry.time)} 的版本（${formatBytes(bytes.length)}）。`,
    count: 1,
    entries: entriesToValue([entry]),
  }
}

async function handleRevertTurn(args, exec) {
  const all = await loadAllEntries(400)
  const sessionId = exec.agent && exec.agent.session && exec.agent.session.header ? String(exec.agent.session.header.id) : ''
  const wanted = args.sessionId ? String(args.sessionId) : sessionId
  let candidates = all.filter((entry) => entry.sessionId === wanted)
  if (!candidates.length) {
    return { action: 'revert_turn', status: 'not_found', message: `会话 ${wanted || '(未知)'} 没有快照记录。`, count: 0, entries: [] }
  }
  let turnId = args.turnId ? String(args.turnId) : ''
  if (!turnId) turnId = candidates[0].sessionTurnId || candidates[0].callId || ''
  candidates = candidates.filter((entry) => (entry.sessionTurnId || entry.callId || '') === turnId)
  if (!candidates.length) {
    return { action: 'revert_turn', status: 'not_found', message: `该会话没有 turnId=${turnId} 的快照。`, count: 0, entries: [] }
  }
  // 同一文件可能有多个代（本轮内被改过多次）；回退到本轮最早那代的「改前版本」= 该文件在本轮开始时的样子。
  const byPath = new Map()
  for (const entry of candidates) {
    const previous = byPath.get(entry.originalPath)
    if (!previous || (entry.time || 0) < (previous.time || 0) || ((entry.time || 0) === (previous.time || 0) && Number(entry.id) < Number(previous.id))) {
      byPath.set(entry.originalPath, entry)
    }
  }
  const restored = []
  const skipped = []
  for (const entry of byPath.values()) {
    if (!entry.restorable) {
      skipped.push(entry.originalPath)
      continue
    }
    const bytes = await readEntryContent(entry)
    if (!bytes) {
      skipped.push(entry.originalPath)
      continue
    }
    const target = resolveTarget(entry.displayPath, entry.workspaceCwd) || entry.originalPath
    try {
      await atomicWrite(target, bytes)
      restored.push(entry)
    } catch {
      skipped.push(entry.originalPath)
    }
  }
  await appendSessionLog({ kind: 'revert_turn', at: Date.now(), sessionId: wanted, turnId, files: restored.map((entry) => entry.originalPath) })
  const message = restored.length
    ? `已回退 ${restored.length} 个文件到本轮修改前的版本${skipped.length ? `；${skipped.length} 个跳过（无内容副本或写入失败）` : ''}。`
    : '没有任何文件被还原。'
  return { action: 'revert_turn', status: restored.length ? 'restored' : 'noop', message, count: restored.length, entries: entriesToValue(restored) }
}

// ─────────────────────────── 插件入口 ───────────────────────────

export const name = 'file-history'

/** 依赖：tools（拦截 + 注册工具）、settings（持久开关）、timer（延迟清理，可选降级）。 */
export const inject = ['tools', 'settings']

export function apply(ctx, config = {}) {
  const settings = ctx.settings.register(SETTINGS_NS, fileHistorySettingsSchema, { base: config })
  let lastSweep = 0

  const currentSettings = () => {
    const value = settings.get() || {}
    return {
      enabled: value.enabled !== false,
      maxFileBytes: Number(value.maxFileBytes) > 0 ? Number(value.maxFileBytes) : DEFAULT_MAX_FILE_BYTES,
      maxAgeDays: Number(value.maxAgeDays) > 0 ? Number(value.maxAgeDays) : DEFAULT_MAX_AGE_DAYS,
      maxWorkspaceBytes: Number(value.maxWorkspaceBytes) > 0 ? Number(value.maxWorkspaceBytes) : DEFAULT_MAX_WORKSPACE_BYTES,
      maxEntriesPerFile: Number(value.maxEntriesPerFile) > 0 ? Number(value.maxEntriesPerFile) : DEFAULT_MAX_ENTRIES_PER_FILE,
    }
  }

  const scheduleSweep = (wsKey, config) => {
    const now = Date.now()
    if (now - lastSweep < SWEEP_INTERVAL_MS) return
    lastSweep = now
    ctx.setTimeout(() => {
      sweepWorkspace(wsKey, config).catch((error) => {
        console.error(`[${PLUGIN}] sweep failed: ${error && error.message ? error.message : error}`)
      })
    }, 5000)
  }

  // 1) 改前快照：失败即拦截，绝不放行一次「没有备份的覆盖」。
  ctx.on('tools/pre-execute', async (exec, next) => {
    const toolName = String(exec.name || '')
    const bare = toolName.includes(':') ? toolName.slice(toolName.lastIndexOf(':') + 1) : toolName
    const config = currentSettings()
    if (!config.enabled || !MUTATING_TOOLS.has(bare)) return next()
    try {
      const meta = await snapshotBeforeWrite(exec, config)
      if (meta) {
        ctx.logger?.debug?.(`[${PLUGIN}] snapshot ${meta.entryId || ''} ${meta.originalPath}`)
        scheduleSweep(meta.workspaceKey, config)
      }
    } catch (error) {
      const reason = error && error.message ? error.message : String(error)
      console.error(`[${PLUGIN}] 快照失败，已拦截 ${bare}: ${reason}`)
      return {
        kind: 'deny',
        reason: `file-history 无法为本次覆盖留备份（${reason}）；已拦下这次 ${bare}，文件未被修改。请检查文件是否被占用/权限是否足够，或改用 dsh-file-history 的 settings（file-history.enabled=false）后重试。`,
      }
    }
    return next()
  })

  // 2) 模型侧唯一新增工具：需要时才调用，平时零 token。
  const fileHistoryTool = {
    name: 'file_history',
    description:
      '文件历史与回滚。任何 write/edit 覆盖已存在文件前，harness 会自动把原文快照到 ~/.dsh/file-history（无需你手动备份）。' +
      'action=list 列出最近的快照；action=show 看某条快照与当前文件的 diff；action=restore 还原单个文件；' +
      'action=revert_turn 把本会话本轮（或指定 sessionId/turnId）改过的文件全部还原。改错、改坏、误删时先用它，不要凭记忆重写。',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        action: { type: 'string', enum: ['list', 'show', 'restore', 'revert_turn'], description: '要执行的操作' },
        path: { type: 'string', description: '目标文件路径（相对当前会话工作区，或用绝对路径）；show/restore 用' },
        entryId: { type: 'string', description: '精确指定快照条目（形如 <workspace>/<file-sig>/0003）；show/restore 用' },
        query: { type: 'string', description: 'list 时按路径子串过滤' },
        scope: { type: 'string', enum: ['all', 'session'], description: 'list 的范围，默认 all；session 只看当前会话' },
        limit: { type: 'number', description: 'list 返回条数上限，默认 20' },
        sessionId: { type: 'string', description: 'revert_turn 指定会话，默认当前会话' },
        turnId: { type: 'string', description: 'revert_turn 指定轮次，默认最近一轮' },
      },
      required: ['action'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          action: { type: 'string' },
          status: { type: 'string' },
          message: { type: 'string' },
          count: { type: 'number' },
          entries: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                entryId: { type: 'string' },
                time: { type: 'string' },
                path: { type: 'string' },
                size: { type: 'number' },
                restorable: { type: 'boolean' },
                note: { type: 'string' },
                tool: { type: 'string' },
              },
              required: ['entryId', 'time', 'path', 'size', 'restorable', 'note', 'tool'],
            },
          },
        },
        required: ['action', 'status', 'message', 'count', 'entries'],
      },
      render(args, value) {
        return [{ type: 'text', text: value.message || '(无输出)' }]
      },
    },
    async execute(args, exec) {
      exec.signal.throwIfAborted()
      try {
        switch (args.action) {
          case 'show':
            return await handleShow(args, exec)
          case 'restore':
            return await handleRestore(args, exec)
          case 'revert_turn':
            return await handleRevertTurn(args, exec)
          default:
            return await handleList(args, exec, currentSettings())
        }
      } catch (error) {
        return {
          action: String(args.action || 'list'),
          status: 'error',
          message: `file_history 执行失败: ${error && error.message ? error.message : error}`,
          count: 0,
          entries: [],
        }
      }
    },
  }
  ctx.tools.register(fileHistoryTool)

  settings.watch((next) => {
    console.log(`[${PLUGIN}] settings changed: enabled=${next.enabled !== false}`)
  })

  ctx.setTimeout(async () => {
    try {
      await mkdir(HISTORY_DIR, { recursive: true })
      const config = currentSettings()
      console.log(`[${PLUGIN}] armed: 覆盖已存在文件前自动快照 → ${HISTORY_DIR} (enabled=${config.enabled})`)
    } catch (error) {
      console.error(`[${PLUGIN}] 无法创建快照目录 ${HISTORY_DIR}: ${error && error.message ? error.message : error}`)
    }
  }, 200)
}
