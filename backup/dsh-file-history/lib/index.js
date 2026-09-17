// dsh-file-history — Host half (static / composition plugin)
//
// 目的：让 harness 在「改文件之前」自动留一份原文备份，不再依赖模型自觉。
//
//  1. 监听 tools/pre-execute：凡是 write / edit 且目标文件已存在 → 先把原文复制进
//     **项目内** <项目根>/.dsh-backup/<源文件相对路径>/<源文件名>.<时间戳>.<扩展名> 再放行。
//     新建文件（原文件不存在）不占用空间。
//  2. 校验：备份必须真的成功，否则**拦截这次写入**（fail-closed），杜绝「没备份却照样改坏」。
//  3. 保留策略：每个源文件只保留最近 N 代（默认 5 轮），另加保留天数与总容量上限。
//  4. 模型侧两个入口：file_history 工具（list / show / restore / revert_turn）+ 系统提示里的
//     一段常驻说明（备份系统存在、位置、如何从检查点恢复）。
//  5. 运行状况标志：<项目根>/.dsh-backup/_dsh-file-history/status.json + manifest.jsonl（人类可读）。
//
// 设计取舍：pre-execute 不能改写 exec.arguments，所以这里不做「挡下写入再由插件代写」——
// 那会丢掉 harness 原生的 read-before-write 校验和展示层 diff 卡片。这里只做旁路备份 + 校验，
// 让原工具照常执行，模型侧的可见行为完全不变。

import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile, readdir, stat, rm, rename, appendFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import path from 'node:path'
import s from '@deepseek-ai/schemastery'

/** 设置命名空间（持久化在 ~/.dsh/settings.yaml 的 file-history 段）。 */
export const SETTINGS_NS = 'file-history'
/** 插件在日志与备份元数据里的标识。 */
export const PLUGIN = 'file-history'
/** 项目内备份目录名（位于会话工作目录下）。 */
export const BACKUP_DIR_NAME = '.dsh-backup'
/** 项目内备份目录里的元数据子目录（状态标志 + manifest + sidecar）。 */
export const META_DIR_NAME = '_dsh-file-history'
/** 项目根之外的文件的兜底备份目录（不进项目，避免污染无关目录）。 */
export const HISTORY_DIR = path.join(homedir(), '.dsh', 'file-history')

const SHORT_HASH_LEN = 16
const DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024
const DEFAULT_MAX_GENERATIONS = 5
const DEFAULT_MAX_AGE_DAYS = 30
const DEFAULT_MAX_PROJECT_BYTES = 512 * 1024 * 1024
const SWEEP_INTERVAL_MS = 60 * 60 * 1000
const DIFF_MAX_LINES = 400
const LCS_BUDGET = 1200

/** 会被备份的文件修改类工具名（真实名 + PTC 限定名两种形态都覆盖）。 */
const MUTATING_TOOLS = new Set(['write', 'edit'])

/** 时间戳格式：20260917-095500。 */
function stampFor(date) {
  const pad = (value) => String(value).padStart(2, '0')
  return (
    `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}` +
    `-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
  )
}

/**
 * 备份文件名：源文件名 + 时间后缀（保留原扩展名，便于双击打开/对比）。
 * 例：app.ts → app.20260917-095500.ts；archive.tar.gz → archive.tar.20260917-095500.gz。
 */
export function backupFileName(sourceName, date = new Date()) {
  const ext = path.extname(sourceName)
  const stem = ext ? sourceName.slice(0, -ext.length) : sourceName
  return `${stem}.${stampFor(date)}${ext}`
}

/** 元数据文件名：与备份同名 + .json。 */
export function sidecarName(backupName) {
  return `${backupName}.json`
}

/**
 * 设置 schema：全部有默认值，用户段落可覆盖。
 * `enabled` 是**全局默认**；`projects` 是**逐项目覆盖**（键＝项目目录绝对路径），
 * 与 dsh-memory-db 的「全局默认 + 每项目覆盖」约定保持一致。
 */
export const fileHistorySettingsSchema = s.object({
  /** 全局默认开关：项目没有单独设置时用它。 */
  enabled: s.boolean().default(true),
  /** 逐项目开关覆盖：{ "<项目目录绝对路径>": true | false }。 */
  projects: s.dict(s.boolean()).default({}),
  /** 超过该字节数的文件只记指纹，不复制内容（避免备份区被大文件撑爆）。 */
  maxFileBytes: s.natural().default(DEFAULT_MAX_FILE_BYTES),
  /** 每个源文件保留多少轮备份（「只保留最近五轮」）。 */
  maxGenerations: s.natural().default(DEFAULT_MAX_GENERATIONS),
  /** 备份保留天数（兜底清理，防止长期不动的项目堆积）。 */
  maxAgeDays: s.natural().default(DEFAULT_MAX_AGE_DAYS),
  /** 单个项目备份区容量上限（字节）。 */
  maxProjectBytes: s.natural().default(DEFAULT_MAX_PROJECT_BYTES),
  /** 是否把「备份系统已启用」写进系统提示，让 agent 知道检查点的存在与位置。 */
  announceInPrompt: s.boolean().default(true),
  /** 是否自动把 .dsh-backup/ 登记进项目 .gitignore（避免备份文件混入 git status / 提交）。 */
  gitignoreBackups: s.boolean().default(true),
})

/** 项目目录 → 覆盖键：统一大小写与分隔符，避免同一个项目因写法不同而分裂成两条。 */
export function projectKeyOf(cwd) {
  if (!cwd || typeof cwd !== 'string') return undefined
  return path.resolve(cwd).replace(/[\\/]+$/, '').toLowerCase()
}

// ───────────────────────────── 小工具 ─────────────────────────────

function sha256(buf) {
  return createHash('sha256').update(buf).digest('hex')
}

function shortHash(text) {
  return sha256(Buffer.from(text, 'utf8')).slice(0, SHORT_HASH_LEN)
}

const WORKSPACE_SKIP = new Set([BACKUP_DIR_NAME, 'node_modules', '.git', '.hg', '.svn', 'dist', 'build', 'out'])

/** 项目内备份根目录（会话工作目录下）。 */
export function backupRootFor(cwd) {
  if (!cwd) return undefined
  return path.join(path.resolve(cwd), BACKUP_DIR_NAME)
}

/** 备份根目录里的元数据目录（状态标志、manifest、sidecar）。 */
export function metaDirFor(cwd) {
  const root = backupRootFor(cwd)
  return root ? path.join(root, META_DIR_NAME) : undefined
}

function workspaceIdentity(cwd) {
  if (!cwd) return { key: 'unknown', name: 'unknown', cwd: '' }
  const resolved = path.resolve(cwd)
  const base = path.basename(resolved) || resolved.replace(/[:\\/]+/g, '_')
  const safe = base.replace(/[^\w\u4e00-\u9fa5.@-]+/g, '_').slice(0, 40) || 'ws'
  return { key: `${safe}-${shortHash(resolved.toLowerCase())}`, name: base, cwd: resolved }
}

function fileSignature(name, absPath) {
  const safe = (name || 'file').replace(/[^\w\u4e00-\u9fa5.@+-]+/g, '_').slice(0, 48) || 'file'
  return `${safe}-${shortHash(absPath.toLowerCase())}`
}

function resolveTarget(target, cwd) {
  if (!target || typeof target !== 'string') return undefined
  if (path.isAbsolute(target)) return path.normalize(target)
  if (!cwd) return undefined
  return path.normalize(path.resolve(cwd, target))
}

/** 目标是否落在项目根内；返回相对项目根的路径。 */
function relativeInsideProject(absPath, projectRoot) {
  if (!projectRoot) return undefined
  const rel = path.relative(path.resolve(projectRoot), absPath)
  if (!rel || rel.startsWith('..') || path.isAbsolute(rel)) return undefined
  return rel
}

function formatBytes(n) {
  if (!Number.isFinite(n)) return '?'
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

function iso(ms) {
  const date = new Date(ms)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value) => String(value).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

function looksBinary(buf) {
  const end = Math.min(buf.length, 8192)
  for (let i = 0; i < end; i += 1) {
    if (buf[i] === 0) return true
  }
  return false
}

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

/** 稳定排序键：时间优先，同毫秒按备份文件名区分。 */
function byNewest(a, b) {
  const delta = (b.time || 0) - (a.time || 0)
  if (delta !== 0) return delta
  return String(b.backupName || '').localeCompare(String(a.backupName || ''))
}

// ─────────────────────────── 备份元数据索引 ───────────────────────────

/** 兜底目录里的条目目录名：新的用时间戳（20260917-095500），旧的用序号（0001）。 */
function normalizeIdentifier(name) {
  const match = /^(\d{8})-(\d{6})$/.exec(name)
  if (match) return `${match[1]}-${match[2]}`
  return /^\d+$/.test(name) ? name : undefined
}

/** 读取项目内备份目录（或兜底目录）里的全部条目。 */
async function readBackupRoot(root, workspaceName) {
  const metaDir = path.join(root, META_DIR_NAME)
  let files
  try {
    files = await readdir(metaDir)
  } catch {
    return []
  }
  const entries = []
  for (const name of files) {
    if (!name.endsWith('.json') || name === 'status.json') continue
    const sidecarPath = path.join(metaDir, name)
    let meta
    try {
      meta = JSON.parse(await readFile(sidecarPath, 'utf8'))
    } catch {
      continue
    }
    if (!meta || meta.kind !== 'snapshot' || !meta.backupPath || !meta.originalPath) continue
    const content = await stat(meta.backupPath).then(
      (value) => ({ stored: value.isFile(), size: value.size }),
      () => ({ stored: false, size: 0 }),
    )
    entries.push({
      ...meta,
      id: meta.id || name.replace(/\.json$/, ''),
      entryId: meta.backupPath,
      dir: root,
      workspaceName: workspaceName || meta.workspaceName || '',
      restorable: Boolean(meta.stored) && content.stored,
      contentSize: content.size,
    })
  }
  return entries
}

/** 读取兜底目录（~/.dsh/file-history/<workspace>/<sig>/<id>）里的条目：新的 id 是时间戳，旧的是序号。 */
async function readLegacyEntries(workspaceKey) {
  const dir = path.join(HISTORY_DIR, workspaceKey)
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
    for (const rawId of ids) {
      const id = normalizeIdentifier(rawId)
      if (!id) continue
      const entryDir = path.join(sigDir, rawId)
      try {
        const meta = JSON.parse(await readFile(path.join(entryDir, 'meta.json'), 'utf8'))
        const stored = await stat(path.join(entryDir, 'content')).then(
          (value) => value.isFile(),
          () => false,
        )
        entries.push({
          ...meta,
          id,
          entryId: `${workspaceKey}/${sig.name}/${id}`,
          dir: entryDir,
          backupPath: path.join(entryDir, 'content'),
          restorable: stored,
        })
      } catch {
        /* 残缺目录跳过 */
      }
    }
  }
  return entries
}

/**
 * 汇总一次调用可见的全部备份：项目内备份目录（主）+ 兜底目录（项目外文件/历史遗留）。
 * @param cwd - 会话工作目录，项目内备份就在它的 .dsh-backup 下。
 * @param extraCwd - 追加查询的项目根（例如根据路径反推），可省略。
 */
async function loadEntries(cwd, extraCwd) {
  const workspace = workspaceIdentity(cwd)
  const roots = new Set()
  const projectRoot = cwd ? path.resolve(cwd) : undefined
  if (projectRoot) roots.add(projectRoot)
  if (extraCwd && path.resolve(extraCwd) !== projectRoot) roots.add(path.resolve(extraCwd))

  const entries = []
  for (const root of roots) {
    const found = await readBackupRoot(backupRootFor(root), path.basename(root))
    for (const entry of found) entries.push({ ...entry, projectRoot: root })
  }
  for (const entry of await readLegacyEntries(workspace.key)) {
    entries.push({ ...entry, projectRoot: undefined, legacy: true })
  }
  entries.sort(byNewest)
  return entries
}

/** 按路径找目标所在的项目根：优先会话 cwd，其次从路径本身推。 */
async function projectRootsFor(absPath, cwd) {
  const roots = []
  if (cwd) roots.push(path.resolve(cwd))
  return roots
}

function matchEntry(entries, args, cwd) {
  if (args.entryId) {
    const wanted = String(args.entryId)
    const byPath = entries.find((entry) => entry.backupPath === wanted || entry.entryId === wanted)
    if (byPath) return byPath
    return entries.find((entry) => entry.id === wanted)
  }
  const abs = resolveTarget(String(args.path || ''), cwd)
  if (!abs) return undefined
  return entries.find((entry) => entry.originalPath === abs)
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
      total += await stat(child).then((value) => value.size, () => 0)
    }
  }
  return total
}

/**
 * 按「每个源文件保留最近 maxGenerations 代」+ 保留天数 + 总容量裁剪项目备份区。
 * 只动 .dsh-backup 内的文件，绝不触碰项目源码。
 */
async function sweepProject(root, settings) {
  const root_ = backupRootFor(root)
  const entries = await readBackupRoot(root_, path.basename(root))
  const cutoff = Date.now() - settings.maxAgeDays * 24 * 60 * 60 * 1000
  const bySource = new Map()
  for (const entry of entries) {
    const list = bySource.get(entry.originalPath) || []
    list.push(entry)
    bySource.set(entry.originalPath, list)
  }
  const removed = []
  const removeEntry = async (entry) => {
    await rm(entry.backupPath, { force: true }).catch(() => {})
    await rm(path.join(entry.dir, META_DIR_NAME, sidecarName(entry.backupName)), { force: true }).catch(() => {})
    await removeEmptyDirs(root_, path.dirname(entry.backupPath)).catch(() => {})
    removed.push(entry.backupPath)
  }
  for (const list of bySource.values()) {
    list.sort(byNewest)
    for (let index = 0; index < list.length; index += 1) {
      const entry = list[index]
      const excess = index >= settings.maxGenerations
      const expired = (entry.time || 0) < cutoff
      if (!excess && !expired) continue
      await removeEntry(entry)
    }
  }
  let total = await dirSize(root_)
  if (total > settings.maxProjectBytes) {
    const oldest = entries.filter((entry) => !removed.includes(entry.backupPath)).sort((a, b) => (a.time || 0) - (b.time || 0))
    for (const entry of oldest) {
      if (total <= settings.maxProjectBytes) break
      total -= await stat(entry.backupPath).then((value) => value.size, () => 0)
      await removeEntry(entry)
    }
  }
  return removed
}

async function removeEmptyDirs(root, startDir) {
  let current = startDir
  const stop = path.resolve(root)
  while (path.resolve(current).startsWith(stop) && path.resolve(current) !== stop) {
    const left = await readdir(current).catch(() => ['x'])
    if (left.length > 0) return
    await rm(current, { recursive: false, force: true }).catch(() => {})
    current = path.dirname(current)
  }
}

/** 兜底目录（~/.dsh/file-history）里旧式条目的清理：同样按代数与天数收敛。 */
async function sweepLegacy(workspaceKey, settings) {
  const root = path.join(HISTORY_DIR, workspaceKey)
  let sigs
  try {
    sigs = await readdir(root, { withFileTypes: true })
  } catch {
    return
  }
  const cutoff = Date.now() - settings.maxAgeDays * 24 * 60 * 60 * 1000
  for (const sig of sigs) {
    if (!sig.isDirectory()) continue
    const sigDir = path.join(root, sig.name)
    const ids = (await readdir(sigDir).catch(() => [])).filter((id) => /^\d+$/.test(id)).sort((a, b) => Number(a) - Number(b))
    const keep = new Set(ids.slice(Math.max(0, ids.length - settings.maxGenerations)))
    for (const id of ids) {
      const entryDir = path.join(sigDir, id)
      const time = await stat(path.join(entryDir, 'meta.json'))
        .then((value) => value.mtimeMs, () => Date.now())
      if (keep.has(id) && time >= cutoff) continue
      await rm(entryDir, { recursive: true, force: true }).catch(() => {})
    }
    await removeEmptyDirs(root, sigDir)
  }
}

// ─────────────────────────── git 卫生 ───────────────────────────

/**
 * 把备份目录登记进项目 .gitignore（只追加一行，绝不重写已有内容）。
 * 目的：备份文件不该混进 git status / git add . / diff 之类的地方。
 * 工作区常是某个仓库的子目录，所以从工作区往上找最近的 git 根，登记带相对路径的条目。
 */
async function ensureGitignored(projectRoot) {
  const start = path.resolve(projectRoot)
  let current = start
  let gitRoot
  for (;;) {
    if (await stat(path.join(current, '.git')).then(() => true, () => false)) {
      gitRoot = current
      break
    }
    const parent = path.dirname(current)
    if (parent === current) break
    current = parent
  }
  if (!gitRoot) return 'no-git'

  // 工作区在仓库内的相对位置；工作区正好是仓库根时 rel === ''。
  const rel = path.relative(gitRoot, start).split(path.sep).filter(Boolean).join('/')
  const entry = rel ? `/${rel}/${BACKUP_DIR_NAME}/` : `${BACKUP_DIR_NAME}/`
  const gitignorePath = path.join(gitRoot, '.gitignore')
  let text = ''
  try {
    text = await readFile(gitignorePath, 'utf8')
  } catch {
    text = ''
  }
  const normalize = (line) => line.trim().replace(/^\/+/, '').replace(/\/+$/, '')
  const wanted = normalize(entry)
  const already = text.split(/\r?\n/).some((line) => normalize(line) === wanted)
  if (already) return 'present'
  const prefix = text.length === 0 ? '' : text.endsWith('\n') ? '\n' : '\n\n'
  await writeFile(
    gitignorePath,
    `${text}${prefix}# dsh-file-history 自动备份（改前检查点），不纳入版本管理\n${entry}\n`,
    'utf8',
  )
  return 'added'
}

// ─────────────────────────── 状态标志 ───────────────────────────

function statusPathFor(cwd) {
  const metaDir = metaDirFor(cwd)
  return metaDir ? path.join(metaDir, 'status.json') : undefined
}

function manifestPathFor(cwd) {
  const metaDir = metaDirFor(cwd)
  return metaDir ? path.join(metaDir, 'manifest.jsonl') : undefined
}

/**
 * 写运行状况标志。status.json 是「备份系统在运行」的小标志：
 * 时间戳每次快照/还原都会刷新，agent 或人看一眼就知道系统还活着。
 */
async function writeStatus(cwd, patch) {
  const statusPath = statusPathFor(cwd)
  if (!statusPath) return undefined
  let previous = {}
  try {
    previous = JSON.parse(await readFile(statusPath, 'utf8'))
  } catch {
    previous = {}
  }
  const next = {
    plugin: PLUGIN,
    status: 'ok',
    at: iso(Date.now()),
    atMs: Date.now(),
    backupDir: backupRootFor(cwd),
    snapshots: (Number(previous.snapshots) || 0) + (patch.counted ? 1 : 0),
    lastBackup: patch.lastBackup || previous.lastBackup || null,
    lastRestore: patch.lastRestore || previous.lastRestore || null,
    lastError: patch.lastError !== undefined ? patch.lastError : previous.lastError || null,
    retainedPerFile: patch.maxGenerations,
    hint: '每个源文件保留最近 N 代；恢复：file_history(action=restore) 或直接复制本目录下的备份文件',
  }
  await atomicWrite(statusPath, `${JSON.stringify(next, null, 2)}\n`).catch(() => {})
  return next
}

async function appendManifest(cwd, record) {
  const manifestPath = manifestPathFor(cwd)
  if (!manifestPath) return
  try {
    await mkdir(path.dirname(manifestPath), { recursive: true })
    await appendFile(manifestPath, `${JSON.stringify(record)}\n`, 'utf8')
  } catch {
    /* 审计日志失败不影响主流程 */
  }
}

// ─────────────────────────── 备份 ───────────────────────────

/**
 * 为一次即将发生的覆盖写入留备份。
 * @returns 成功返回条目；无需备份返回 undefined；失败抛错（调用方据此拦截写入）。
 */
async function backupBeforeWrite(exec, settings) {
  const args = exec.arguments && typeof exec.arguments === 'object' ? exec.arguments : {}
  const requested = typeof args.file_path === 'string' ? args.file_path : undefined
  const agent = exec.agent
  const header = agent && agent.session ? agent.session.header : undefined
  const cwd = header && header.cwd ? header.cwd : undefined
  const absPath = resolveTarget(requested, cwd)
  if (!absPath) return undefined

  // 绝不备份备份区自身（否则会自噬式增长）。
  const projectRoot = cwd ? path.resolve(cwd) : undefined
  if (projectRoot) {
    const relFromRoot = path.relative(projectRoot, absPath)
    if (relFromRoot && (relFromRoot === BACKUP_DIR_NAME || relFromRoot.startsWith(`${BACKUP_DIR_NAME}${path.sep}`))) return undefined
  }
  if (absPath.startsWith(HISTORY_DIR)) return undefined

  let st
  try {
    st = await stat(absPath)
  } catch {
    return undefined // 新建文件：没有原内容可保护
  }
  if (!st.isFile() || st.size === 0) return undefined

  const insideRel = relativeInsideProject(absPath, projectRoot)
  const workspace = workspaceIdentity(cwd)
  const now = new Date()
  const sourceName = path.basename(absPath)

  let backupPath
  let metaDir
  let entryDir
  if (insideRel) {
    // 项目内：<项目根>/.dsh-backup/<源文件相对路径>/<源文件名>.<时间戳>.<扩展名>
    const destDir = path.join(backupRootFor(projectRoot), path.dirname(insideRel))
    await mkdir(destDir, { recursive: true })
    let candidate = backupFileName(sourceName, now)
    let attempt = 1
    while (await stat(path.join(destDir, candidate)).then(() => true, () => false)) {
      attempt += 1
      candidate = backupFileName(sourceName, new Date(now.getTime() + attempt * 1000))
    }
    backupPath = path.join(destDir, candidate)
    metaDir = metaDirFor(projectRoot)
  } else {
    // 项目外：落到兜底目录，不进无关项目
    const sig = fileSignature(sourceName, absPath)
    const stamp = stampFor(now)
    const destDir = path.join(HISTORY_DIR, workspace.key, sig, stamp)
    await mkdir(destDir, { recursive: true })
    backupPath = path.join(destDir, 'content')
    metaDir = destDir
  }
  await mkdir(metaDir, { recursive: true })
  await mkdir(path.dirname(backupPath), { recursive: true })

  const backupName = path.basename(backupPath)
  const tooLarge = st.size > settings.maxFileBytes
  let bytes
  if (!tooLarge) {
    try {
      bytes = await readWithRetry(absPath)
    } catch (error) {
      throw new Error(`无法读取原文件用于备份: ${error && error.message ? error.message : error}`)
    }
  }

  const binary = bytes ? looksBinary(bytes) : false
  const storeContent = Boolean(bytes) && !binary

  if (storeContent) {
    // 写盘期间原文件若已被改动（mtime/size 变化），这份备份就不再是「改前版本」，宁可丢弃也不能留错版。
    const after = await stat(absPath).catch(() => undefined)
    if (!after || after.mtimeMs !== st.mtimeMs || after.size !== st.size) {
      throw new Error('原文件在备份期间被并发修改，已放弃本次备份（写入未执行）')
    }
    await writeFile(backupPath, bytes)
  }

  const fingerprint = bytes ? sha256(bytes) : shortHash(`${st.size}:${st.mtimeMs}`)
  const sessionId = header && header.id ? String(header.id) : ''
  const meta = {
    kind: 'snapshot',
    id: backupName,
    time: Date.now(),
    sourceMtimeMs: st.mtimeMs,
    originalPath: absPath,
    displayPath: requested || absPath,
    relativePath: insideRel || '',
    inProject: Boolean(insideRel),
    backupPath,
    backupName,
    workspaceKey: workspace.key,
    workspaceName: workspace.name,
    workspaceCwd: workspace.cwd,
    projectRoot: projectRoot || '',
    size: st.size,
    hash: fingerprint,
    hashKind: bytes ? 'sha256' : 'size+mtime',
    tool: exec.name,
    stored: storeContent,
    binary,
    reason: storeContent ? '' : binary ? '二进制文件只记指纹' : `超过 ${formatBytes(settings.maxFileBytes)} 只记指纹`,
    callId: String(exec.callId || ''),
    sessionId,
    sessionTitle: header && header.title ? String(header.title).slice(0, 200) : '',
    sessionTurnId: String(exec.rootCallId || ''),
  }

  const sidecar = path.join(metaDir, insideRel ? sidecarName(backupName) : 'meta.json')
  await writeFile(sidecar, `${JSON.stringify(meta, null, 2)}\n`, 'utf8')

  await appendManifest(projectRoot, {
    kind: 'snapshot',
    at: iso(meta.time),
    source: absPath,
    backup: backupPath,
    tool: meta.tool,
    session: sessionId,
    stored: meta.stored,
  })
  await writeStatus(projectRoot, {
    counted: true,
    lastBackup: { path: absPath, backup: backupPath, at: iso(meta.time) },
    maxGenerations: settings.maxGenerations,
    lastError: null,
  })
  if (settings.gitignoreBackups && projectRoot) {
    await ensureGitignored(projectRoot).catch(() => {})
  }
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
    while (i < n) {
      result.push(`- ${a[i]}`)
      i += 1
    }
    while (j < m) {
      result.push(`+ ${b[j]}`)
      j += 1
    }
  }
  for (let k = endOld; k < oldLines.length; k += 1) result.push(`  ${oldLines[k]}`)
  return result
}

// ─────────────────────────── 工具实现 ───────────────────────────

function entriesToValue(entries) {
  return entries.map((entry) => ({
    entryId: entry.backupPath,
    time: iso(entry.time),
    path: entry.originalPath,
    size: entry.size,
    restorable: Boolean(entry.restorable),
    note: entry.reason || '',
    tool: entry.tool || '',
  }))
}

function cwdOf(exec) {
  const header = exec.agent && exec.agent.session ? exec.agent.session.header : undefined
  return header && header.cwd ? header.cwd : undefined
}

function sessionIdOf(exec) {
  const header = exec.agent && exec.agent.session ? exec.agent.session.header : undefined
  return header && header.id ? String(header.id) : ''
}

async function handleList(args, exec, settings) {
  const cwd = cwdOf(exec)
  const limit = Math.max(1, Math.min(Number(args.limit) || 20, 100))
  let entries = await loadEntries(cwd)
  if (args.scope === 'session' && sessionIdOf(exec)) {
    entries = entries.filter((entry) => entry.sessionId === sessionIdOf(exec))
  }
  if (typeof args.query === 'string' && args.query.trim()) {
    const needle = args.query.trim().toLowerCase()
    entries = entries.filter((entry) => String(entry.originalPath).toLowerCase().includes(needle))
  }
  const slice = entries.slice(0, limit)
  const statusPath = statusPathFor(cwd)
  const dir = backupRootFor(cwd)
  const message = slice.length
    ? `最近 ${slice.length} 条备份（每个源文件保留最近 ${settings.maxGenerations} 代，超过即自动清理）\n备份目录: ${dir}\n运行状况: ${statusPath}`
    : `没有匹配的备份记录。备份目录: ${dir}；运行状况标志: ${statusPath}\n（只有「覆盖已存在文件」的 write/edit 才会产生备份。）`
  return { action: 'list', status: slice.length ? 'ok' : 'empty', message, count: slice.length, entries: entriesToValue(slice) }
}

async function handleShow(args, exec) {
  const cwd = cwdOf(exec)
  const entries = await loadEntries(cwd)
  const entry = matchEntry(entries, args, cwd)
  if (!entry) return { action: 'show', status: 'not_found', message: '没找到对应备份；可用 action=list 查看可用条目。', count: 0, entries: [] }
  const head = [
    `备份 ${entry.backupName}`,
    `原文件: ${entry.originalPath}`,
    `备份文件: ${entry.backupPath}`,
    `时间: ${iso(entry.time)}  大小: ${formatBytes(entry.size)}  工具: ${entry.tool}`,
  ]
  if (!entry.restorable) {
    head.push(`无内容副本（${entry.reason}），只能确认「改前状态」：${entry.hashKind}=${entry.hash}`)
    return { action: 'show', status: 'meta_only', message: head.join('\n'), count: 1, entries: entriesToValue([entry]) }
  }
  const beforeBytes = await readFile(entry.backupPath)
  const afterBytes = await readFile(entry.originalPath).catch(() => undefined)
  const before = splitLines(beforeBytes.toString('utf8'))
  if (!afterBytes) {
    head.push('当前文件已不存在（被删除或改名），下面是备份内容全文：')
    const body = before.slice(0, DIFF_MAX_LINES).map((line) => `  ${line}`)
    if (before.length > DIFF_MAX_LINES) body.push(`  …（还有 ${before.length - DIFF_MAX_LINES} 行，未显示）`)
    return { action: 'show', status: 'deleted', message: `${head.join('\n')}\n${body.join('\n')}`, count: 1, entries: entriesToValue([entry]) }
  }
  const diff = diffLines(before, splitLines(afterBytes.toString('utf8')))
  const shown = diff.slice(0, DIFF_MAX_LINES)
  const tail = diff.length > shown.length ? `\n…（diff 共 ${diff.length} 行，已截断）` : ''
  const changed = diff.some((line) => line.startsWith('- ') || line.startsWith('+ '))
  head.push(`对比当前文件（- 改前 / + 现在）${changed ? '' : '：内容一致'}`)
  return { action: 'show', status: 'ok', message: `${head.join('\n')}\n${shown.join('\n')}${tail}`, count: 1, entries: entriesToValue([entry]) }
}

async function handleRestore(args, exec) {
  const cwd = cwdOf(exec)
  const entries = await loadEntries(cwd)
  const entry = matchEntry(entries, args, cwd)
  if (!entry) return { action: 'restore', status: 'not_found', message: '没找到对应备份，未做任何修改。', count: 0, entries: [] }
  if (!entry.restorable) {
    return { action: 'restore', status: 'meta_only', message: `该备份没有内容副本（${entry.reason}），无法还原。`, count: 0, entries: entriesToValue([entry]) }
  }
  const bytes = await readFile(entry.backupPath).catch(() => undefined)
  if (!bytes) return { action: 'restore', status: 'error', message: '备份内容不可读或已被清理。', count: 0, entries: [] }
  await atomicWrite(entry.originalPath, bytes)
  await appendManifest(entry.projectRoot || cwd, {
    kind: 'restore',
    at: iso(Date.now()),
    source: entry.originalPath,
    backup: entry.backupPath,
    session: sessionIdOf(exec),
  })
  await writeStatus(entry.projectRoot || cwd, {
    lastRestore: { path: entry.originalPath, backup: entry.backupPath, at: iso(Date.now()) },
  })
  return {
    action: 'restore',
    status: 'restored',
    message: `已把 ${entry.originalPath} 还原为 ${iso(entry.time)} 的备份（${formatBytes(bytes.length)}）。`,
    count: 1,
    entries: entriesToValue([entry]),
  }
}

async function handleRevertTurn(args, exec) {
  const cwd = cwdOf(exec)
  const entries = await loadEntries(cwd)
  const sessionId = args.sessionId ? String(args.sessionId) : sessionIdOf(exec)
  let candidates = entries.filter((entry) => entry.sessionId === sessionId)
  if (!candidates.length) {
    return { action: 'revert_turn', status: 'not_found', message: `会话 ${sessionId || '(未知)'} 没有备份记录。`, count: 0, entries: [] }
  }
  let turnId = args.turnId ? String(args.turnId) : ''
  if (!turnId) turnId = candidates[0].sessionTurnId || ''
  candidates = candidates.filter((entry) => (entry.sessionTurnId || '') === turnId)
  if (!candidates.length) {
    return { action: 'revert_turn', status: 'not_found', message: `该会话没有 turnId=${turnId} 的备份。`, count: 0, entries: [] }
  }
  // 同一文件可能有多个代；回退到本轮最早那代 = 该文件在本轮开始时的样子。
  const byPath = new Map()
  for (const entry of candidates) {
    const previous = byPath.get(entry.originalPath)
    if (!previous || (entry.time || 0) < (previous.time || 0)) byPath.set(entry.originalPath, entry)
  }
  const restored = []
  const skipped = []
  for (const entry of byPath.values()) {
    if (!entry.restorable) {
      skipped.push(entry.originalPath)
      continue
    }
    const bytes = await readFile(entry.backupPath).catch(() => undefined)
    if (!bytes) {
      skipped.push(entry.originalPath)
      continue
    }
    try {
      await atomicWrite(entry.originalPath, bytes)
      restored.push(entry)
    } catch {
      skipped.push(entry.originalPath)
    }
  }
  const projectRoot = restored[0] && restored[0].projectRoot ? restored[0].projectRoot : cwd
  await appendManifest(projectRoot, {
    kind: 'revert_turn',
    at: iso(Date.now()),
    session: sessionId,
    turnId,
    files: restored.map((entry) => entry.originalPath),
  })
  const message = restored.length
    ? `已回退 ${restored.length} 个文件到本轮修改前的版本${skipped.length ? `；${skipped.length} 个跳过（无内容副本或写入失败）` : ''}。`
    : '没有任何文件被还原。'
  return { action: 'revert_turn', status: restored.length ? 'restored' : 'noop', message, count: restored.length, entries: entriesToValue(restored) }
}

// ─────────────────────────── 客户端观测面板的 RPC ───────────────────────────

/** 供右上角状态芯片读取的最近流水条数。 */
const RECENT_EVENT_LIMIT = 30

function statusPathOf(cwd) {
  const metaDir = metaDirFor(cwd)
  return metaDir ? path.join(metaDir, 'status.json') : undefined
}

function manifestPathOf(cwd) {
  const metaDir = metaDirFor(cwd)
  return metaDir ? path.join(metaDir, 'manifest.jsonl') : undefined
}

async function readStatusFile(cwd) {
  const statusPath = statusPathOf(cwd)
  if (!statusPath) return undefined
  try {
    return JSON.parse(await readFile(statusPath, 'utf8'))
  } catch {
    return undefined
  }
}

/** 读 manifest 尾部若干条（只解析最后 256KB，避免大流水拖慢面板）。 */
async function readRecentEvents(cwd, limit = RECENT_EVENT_LIMIT) {
  const manifestPath = manifestPathOf(cwd)
  if (!manifestPath) return []
  let text
  try {
    const raw = await readFile(manifestPath)
    // 只看尾部：从后往前找足够多的换行，避免整份流水都做 JSON.parse。
    const tail = raw.length > 256 * 1024 ? raw.subarray(raw.length - 256 * 1024) : raw
    text = tail.toString('utf8')
    if (raw.length > 256 * 1024) {
      // 截断处可能落在半行上，丢掉第一个不完整行。
      const firstBreak = text.indexOf('\n')
      if (firstBreak >= 0) text = text.slice(firstBreak + 1)
    }
  } catch (error) {
    // 不留痕的空 catch 曾经把「读不到流水」藏了半天，这里至少吵一声。
    console.error(`[${PLUGIN}] 读取 manifest 失败: ${error && error.message ? error.message : error}`)
    return []
  }
  const lines = text.split(/\r?\n/).filter(Boolean)
  const events = []
  for (const line of lines.slice(-limit).reverse()) {
    try {
      const row = JSON.parse(line)
      events.push({
        at: row.at || '',
        kind: row.kind || '',
        file: row.source ? path.basename(row.source) : '',
        source: row.source || '',
        backup: row.backup || '',
      })
    } catch {
      /* 半行或损坏行跳过 */
    }
  }
  return events
}

// ─────────────────────────── 插件入口 ───────────────────────────

export const name = 'file-history'

/** 依赖：tools（拦截 + 注册工具）、settings（持久开关）、timer（延迟清理）、agents（按会话解析项目目录）。 */
export const inject = ['tools', 'settings', 'timer', 'agents']

/** 客户端观测面板（右上角状态芯片）使用的 RPC 路由。 */
export const CLIENT_ROUTE = '/dsh-file-history/api'

export function apply(ctx, config = {}) {
  const settings = ctx.settings.register(SETTINGS_NS, fileHistorySettingsSchema, { base: config })
  const systemPrompt = ctx.get('systemPrompt')
  let lastSweep = 0

  /**
   * 解析当前生效的设置。
   * @param cwd - 传项目目录时按「项目覆盖 > 全局默认」求 enabled；不传则只给全局默认值。
   */
  const currentSettings = (cwd) => {
    const value = settings.get() || {}
    const projects = value.projects && typeof value.projects === 'object' ? value.projects : {}
    const key = projectKeyOf(cwd)
    const override = key && Object.prototype.hasOwnProperty.call(projects, key) ? projects[key] : undefined
    const globalEnabled = value.enabled !== false
    return {
      enabled: typeof override === 'boolean' ? override : globalEnabled,
      globalEnabled,
      projectOverride: typeof override === 'boolean' ? override : undefined,
      projectKey: key,
      maxFileBytes: Number(value.maxFileBytes) > 0 ? Number(value.maxFileBytes) : DEFAULT_MAX_FILE_BYTES,
      maxGenerations: Number(value.maxGenerations) > 0 ? Number(value.maxGenerations) : DEFAULT_MAX_GENERATIONS,
      maxAgeDays: Number(value.maxAgeDays) > 0 ? Number(value.maxAgeDays) : DEFAULT_MAX_AGE_DAYS,
      maxProjectBytes: Number(value.maxProjectBytes) > 0 ? Number(value.maxProjectBytes) : DEFAULT_MAX_PROJECT_BYTES,
      announceInPrompt: value.announceInPrompt !== false,
      gitignoreBackups: value.gitignoreBackups !== false,
    }
  }

  // 项目备份区：把某个源文件的备份收敛到最近 maxGenerations 代（「只保留最近五轮」的就地执行）。
  const pruneSource = async (projectRoot, sourcePath, maxGenerations) => {
    const backupRoot = backupRootFor(projectRoot)
    const metaDir = metaDirFor(projectRoot)
    const existing = (await readBackupRoot(backupRoot, path.basename(projectRoot)))
      .filter((entry) => entry.originalPath === sourcePath)
      .sort(byNewest)
    for (const entry of existing.slice(maxGenerations)) {
      await rm(entry.backupPath, { force: true }).catch(() => {})
      await rm(path.join(metaDir, sidecarName(entry.backupName)), { force: true }).catch(() => {})
      await removeEmptyDirs(backupRoot, path.dirname(entry.backupPath)).catch(() => {})
    }
  }

  const scheduleSweep = (root, config, workspaceKey) => {
    const now = Date.now()
    if (now - lastSweep < SWEEP_INTERVAL_MS) return
    lastSweep = now
    // ctx.timeout()（而非已 deprecated 的 ctx.setTimeout）：回调随插件 fiber 自动 dispose。
    ctx.timeout(() => {
      sweepProject(root, config).catch((error) => {
        console.error(`[${PLUGIN}] sweep failed: ${error && error.message ? error.message : error}`)
      })
      if (workspaceKey) {
        sweepLegacy(workspaceKey, config).catch((error) => {
          console.error(`[${PLUGIN}] legacy sweep failed: ${error && error.message ? error.message : error}`)
        })
      }
    }, 5000)
  }

  // 1) 改前备份：失败即拦截，绝不放行一次「没有备份的覆盖」。
  ctx.on('tools/pre-execute', async (exec, next) => {
    const toolName = String(exec.name || '')
    const bare = toolName.includes(':') ? toolName.slice(toolName.lastIndexOf(':') + 1) : toolName
    // 开关是项目级的：按「正在被写的这个项目」求值（项目覆盖 > 全局默认）。
    const config = currentSettings(cwdOf(exec))
    if (!config.enabled || !MUTATING_TOOLS.has(bare)) return next()
    try {
      const meta = await backupBeforeWrite(exec, config)
      if (meta) {
        if (meta.inProject && meta.projectRoot) {
          await pruneSource(meta.projectRoot, meta.originalPath, config.maxGenerations)
          scheduleSweep(meta.projectRoot, config, meta.workspaceKey)
        } else {
          scheduleSweep(meta.projectRoot || (meta.workspaceCwd || process.cwd()), config, meta.workspaceKey)
        }
      }
    } catch (error) {
      const reason = error && error.message ? error.message : String(error)
      console.error(`[${PLUGIN}] 备份失败，已拦截 ${bare}: ${reason}`)
      const cwd = cwdOf(exec)
      if (cwd) await writeStatus(cwd, { lastError: { at: iso(Date.now()), tool: bare, reason } })
      return {
        kind: 'deny',
        reason:
          `file-history 无法为本次覆盖留备份（${reason}）；已拦下这次 ${bare}，文件未被修改。` +
          `请检查文件是否被占用/权限是否足够；确认不影响时可临时在 settings.yaml 把 file-history.enabled 设为 false 后重试。`,
      }
    }
    return next()
  })

  // 2) 模型侧工具：需要时才调用，平时零 token。
  const fileHistoryTool = {
    name: 'file_history',
    description:
      '文件备份与回滚。harness 会在任何 write/edit 覆盖已存在文件之前，自动把原文备份进项目内的 .dsh-backup/ 目录' +
      '（按源路径镜像，文件名＝源文件名+时间戳，每个文件只保留最近几代），你不需要自己复制 .bak。' +
      'action=list 列出最近的备份；action=show 看某条备份与当前文件的 diff；action=restore 还原单个文件；' +
      'action=revert_turn 把本会话本轮（或指定 sessionId/turnId）改过的文件全部还原。改错、改坏、误删时先用它，不要凭记忆重写。',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        action: { type: 'string', enum: ['list', 'show', 'restore', 'revert_turn'], description: '要执行的操作' },
        path: { type: 'string', description: '目标文件路径（相对当前会话工作区，或用绝对路径）；show/restore 用' },
        entryId: { type: 'string', description: '精确指定备份条目（备份文件的绝对路径）；show/restore 用' },
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

  // 3) 让 agent 知道备份系统的存在、位置与恢复方式（每轮只占几行）。
  if (systemPrompt) {
    systemPrompt.section({
      name: 'file-history:usage',
      order: 151,
      text: (context) => {
        try {
          const agent = context && context.agent
          const header = agent && agent.session ? agent.session.header : undefined
          const cwd = header && header.cwd ? header.cwd : undefined
          if (!cwd) return ''
          // 项目级开关：本项目被单独关掉时，这一段就不该出现（否则 agent 会以为有备份）。
          const config = currentSettings(cwd)
          if (!config.enabled || !config.announceInPrompt) return ''
          const root = backupRootFor(cwd)
          const statusPath = statusPathFor(cwd)
          return [
            '## 文件备份与回滚',
            `本会话已启用「改前自动备份」：任何 write/edit 覆盖已存在文件之前，harness 会自动把原文复制到 \`${root}/\`，`,
            '按源文件路径镜像存放，文件名为「源文件名.<时间戳>.<原扩展名>」，每个源文件只保留最近几代（超出自动清理）。',
            `运行状况标志（每次备份/还原都会刷新时间戳）：\`${statusPath}\`；备份清单：\`${path.join(metaDirFor(cwd), 'manifest.jsonl')}\`。`,
            '因此你不需要自己创建 .bak 副本，也不要把备份文件复制进源码目录。',
            `改错、改坏或误删时，先用 file_history 工具恢复，不要凭记忆重写：`,
            '- `file_history(action="list")` 看最近备份；`action="show", path=...` 看与当前文件的 diff；',
            '- `action="restore", path=...` 还原单个文件；`action="revert_turn"` 回退本会话最近一轮改过的所有文件；',
            `- 也可以直接把 \`${root}\` 下的对应备份文件复制回原位。`,
          ].join('\n')
        } catch {
          return ''
        }
      },
    })
  }

  // 4) 右上角状态芯片的 RPC：把 status.json + manifest 尾部 + 开关打包给客户端。
  const agents = ctx.get('agents')
  const webServer = ctx.get('webServer')
  if (webServer) {
    const projectOf = (sessionId) => {
      const agent = sessionId && agents ? agents.get(sessionId) : undefined
      const header = agent && agent.session ? agent.session.header : undefined
      if (header && header.cwd) return { cwd: header.cwd, sessionId: header.id ? String(header.id) : String(sessionId || '') }
      return { cwd: process.cwd(), sessionId: String(sessionId || '') }
    }

    const dispatch = async (method, args) => {
      const sessionId = typeof args.sessionId === 'string' ? args.sessionId : undefined
      const projectCwd = projectOf(sessionId).cwd
      const projectKey = projectKeyOf(projectCwd)

      // 逐项目开关：scope=project 写本项目覆盖；scope=global 改全局默认；reset 删除本项目覆盖。
      if (method === 'set-enabled' || method === 'reset-project') {
        if (method === 'reset-project') {
          if (!projectKey) return { ok: false, reason: 'no-project' }
          await ctx.settings.mutate(SETTINGS_NS, [{ op: 'unset', path: ['projects', projectKey] }])
          const after = currentSettings(projectCwd)
          return { ok: true, enabled: after.enabled, scope: 'inherit', projectOverride: null, globalEnabled: after.globalEnabled }
        }
        const wanted = typeof args.enabled === 'boolean' ? args.enabled : undefined
        if (wanted === undefined) return { ok: false, reason: 'bad-args' }
        const scope = args.scope === 'global' ? 'global' : 'project'
        if (scope === 'global') {
          await settings.update({ enabled: wanted })
        } else {
          if (!projectKey) return { ok: false, reason: 'no-project' }
          await ctx.settings.mutate(SETTINGS_NS, [{ op: 'set', path: ['projects', projectKey], value: wanted }])
        }
        const after = currentSettings(projectCwd)
        return {
          ok: true,
          enabled: after.enabled,
          scope,
          projectOverride: typeof after.projectOverride === 'boolean' ? after.projectOverride : null,
          globalEnabled: after.globalEnabled,
        }
      }

      const cwd = projectCwd
      const config = currentSettings(cwd)
      const status = await readStatusFile(cwd)
      const events = await readRecentEvents(cwd)
      const stat = await (async () => {
        const backupRoot = backupRootFor(cwd)
        let count = 0
        let bytes = 0
        const metaDir = metaDirFor(cwd)
        if (!metaDir) return { count: 0, bytes: 0 }
        for (const name of await readdir(metaDir).catch(() => [])) {
          if (!name.endsWith('.json') || name === 'status.json') continue
          count += 1
          try {
            const meta = JSON.parse(await readFile(path.join(metaDir, name), 'utf8'))
            bytes += Number(meta.size) || 0
          } catch {
            /* 忽略坏 sidecar */
          }
        }
        void backupRoot
        return { count, bytes }
      })()
      return {
        ok: true,
        projectDir: cwd,
        projectName: path.basename(cwd),
        status: status || null,
        statusPath: statusPathOf(cwd),
        manifestPath: manifestPathOf(cwd),
        backupDir: backupRootFor(cwd),
        events,
        stat,
        settings: {
          // enabled 是「本项目生效值」；scope 说明它来自项目覆盖还是全局默认。
          enabled: config.enabled,
          globalEnabled: config.globalEnabled,
          projectOverride: typeof config.projectOverride === 'boolean' ? config.projectOverride : null,
          scope: typeof config.projectOverride === 'boolean' ? 'project' : 'inherit',
          maxGenerations: config.maxGenerations,
          maxFileBytes: config.maxFileBytes,
        },
        refreshedAt: Date.now(),
      }
    }

    const disposeRoute = webServer.register({
      kind: 'exact',
      path: CLIENT_ROUTE,
      handler: async (req, res) => {
        const send = (statusCode, body) => {
          res.writeHead(statusCode, { 'Content-Type': 'application/json; charset=utf-8' })
          res.end(JSON.stringify(body))
        }
        if ((req.method || 'GET') !== 'POST') return send(405, { ok: false, reason: 'method-not-allowed' })
        let raw = ''
        try {
          for await (const chunk of req) raw += chunk
        } catch {
          return send(400, { ok: false, reason: 'read-failed' })
        }
        let request
        try {
          request = JSON.parse(raw)
        } catch {
          return send(400, { ok: false, reason: 'bad-json' })
        }
        const method = request && typeof request.method === 'string' ? request.method : ''
        const args = request && typeof request.args === 'object' && request.args !== null ? request.args : {}
        try {
          send(200, await dispatch(method, args))
        } catch (error) {
          send(200, { ok: false, reason: error instanceof Error ? error.message : String(error) })
        }
      },
    })
    ctx.effect(() => disposeRoute)
    console.log(`[${PLUGIN}] client panel route registered at ${CLIENT_ROUTE}`)
  } else {
    console.warn(`[${PLUGIN}] webServer 不可用：右上角状态面板不会工作（不影响备份本身）`)
  }

  settings.watch((next) => {
    console.log(`[${PLUGIN}] settings changed: enabled=${next.enabled !== false} generations=${next.maxGenerations}`)
  })

  ctx.timeout(async () => {
    try {
      const cwd = process.cwd()
      const metaDir = metaDirFor(cwd)
      if (metaDir) await mkdir(metaDir, { recursive: true })
      console.log(`[${PLUGIN}] armed: 覆盖前自动备份 → <项目根>/${BACKUP_DIR_NAME}/（每个文件保留最近 ${currentSettings().maxGenerations} 代）; 兜底目录 ${HISTORY_DIR}`)
    } catch (error) {
      console.error(`[${PLUGIN}] 初始化失败: ${error && error.message ? error.message : error}`)
    }
  }, 200)
}
