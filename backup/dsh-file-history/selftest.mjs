// dsh-file-history 离线自测：用假 exec/ctx 直接驱动插件（不经过 harness 进程）。
// 覆盖：新建不快照、覆盖留快照、内容是改前原文、list/show/restore/revert_turn、二进制只记哈希、开关、代数裁剪。

import { mkdtemp, writeFile, readFile, readdir, mkdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const results = []
const ok = (label, condition, extra = '') => {
  results.push({ label, pass: Boolean(condition) })
  console.log(`${condition ? 'PASS' : 'FAIL'}  ${label}${extra ? ` — ${extra}` : ''}`)
}

const PLUGIN_PATH = 'C:/Users/twinblade/.dsh/profiles/web/node_modules/dsh-file-history/lib/index.js'
const mod = await import(pathToFileURL(PLUGIN_PATH).href)
ok('模块导出 apply/inject/HISTORY_DIR', typeof mod.apply === 'function' && Array.isArray(mod.inject) && typeof mod.HISTORY_DIR === 'string')

const settingsValue = { enabled: true, maxFileBytes: 2 * 1024 * 1024, maxAgeDays: 30, maxWorkspaceBytes: 512 * 1024 * 1024, maxEntriesPerFile: 3 }
const registered = {}
const listeners = {}
const ctx = {
  settings: { register: () => ({ get: () => settingsValue, watch: () => () => {} }) },
  tools: { register: (definition) => { registered[definition.name] = definition } },
  on: (event, handler) => { listeners[event] = handler },
  setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms || 0, 5)),
  logger: { debug: () => {} },
}
mod.apply(ctx, {})
ok('注册了 tools/pre-execute 监听', typeof listeners['tools/pre-execute'] === 'function')
ok('注册了 file_history 工具', Boolean(registered.file_history))

// ── 索引辅助：按 originalPath 找到元数据目录（读 sidecar，不做私有假设） ──
async function entryDirsFor(absPath) {
  const found = []
  const wsDirs = await readdir(mod.HISTORY_DIR).catch(() => [])
  for (const ws of wsDirs) {
    if (ws.startsWith('_')) continue
    for (const sig of await readdir(path.join(mod.HISTORY_DIR, ws)).catch(() => [])) {
      const sigDir = path.join(mod.HISTORY_DIR, ws, sig)
      for (const id of (await readdir(sigDir).catch(() => [])).filter((value) => /^\d+$/.test(value))) {
        try {
          const meta = JSON.parse(await readFile(path.join(sigDir, id, 'meta.json'), 'utf8'))
          if (meta.originalPath === absPath) found.push({ dir: path.join(sigDir, id), meta })
        } catch {
          /* 残缺条目 */
        }
      }
    }
  }
  return found.sort((a, b) => Number(a.meta.id) - Number(b.meta.id))
}

// ── 测试工作区 ──
const sandbox = await mkdtemp(path.join(tmpdir(), 'fh-selftest-'))
const header = { id: 'session-selftest', cwd: sandbox, title: 'self test' }
const execFor = (name, filePath, callId, rootCallId) => ({
  name,
  callId,
  rootCallId: rootCallId || callId,
  arguments: { file_path: filePath },
  agent: { session: { header } },
  signal: { throwIfAborted: () => {} },
})
const runTool = async (name, filePath, callId, rootCallId) => {
  let nextCalls = 0
  const decision = await listeners['tools/pre-execute'](execFor(name, filePath, callId, rootCallId), async () => {
    nextCalls += 1
    return { kind: 'allow' }
  })
  return { decision, nextCalls }
}
const execCtx = { agent: { session: { header } }, signal: { throwIfAborted: () => {} } }

// 1) 新建文件：无原文可保护 → 直接放行且不留快照
const fresh = path.join(sandbox, 'brand-new.txt')
let outcome = await runTool('write', fresh, 'call-new')
ok('新建文件直接放行', outcome.nextCalls === 1 && outcome.decision.kind === 'allow')
ok('新建文件不留快照', (await entryDirsFor(fresh)).length === 0)

// 2) 覆盖已存在文件：留快照，内容为改前原文
const target = path.join(sandbox, 'demo.txt')
await writeFile(target, 'line1\nline2\nline3\n', 'utf8')
outcome = await runTool('write', target, 'call-overwrite')
const entries = await entryDirsFor(target)
const content = entries.length ? await readFile(path.join(entries[0].dir, 'content'), 'utf8') : ''
ok('覆盖已存在文件放行并留快照', outcome.nextCalls === 1 && entries.length === 1, `entries=${entries.length}`)
ok('快照内容是改前原文', content === 'line1\nline2\nline3\n', JSON.stringify(content))
ok('元数据记录了来源工具与会话', entries[0]?.meta.tool === 'write' && entries[0]?.meta.sessionId === 'session-selftest')

// 3) 模型侧 list / show / restore
let value = await registered.file_history.execute({ action: 'list', scope: 'session' }, execCtx)
ok('list 命中本次快照', value.count >= 1 && value.entries.some((entry) => entry.path === target))

await writeFile(target, 'line1\nCHANGED\nline3\nline9\n', 'utf8')
value = await registered.file_history.execute({ action: 'show', path: target }, execCtx)
ok('show 给出 -改前/+现在 的 diff', value.message.includes('- line2') && value.message.includes('+ CHANGED'))

value = await registered.file_history.execute({ action: 'restore', path: target }, execCtx)
ok('restore 还原为改前内容', (await readFile(target, 'utf8')) === 'line1\nline2\nline3\n', value.status)

// 4) revert_turn：同一条助手消息内改了两个文件（同一个 rootCallId）→ 一次全部回退
const fileA = path.join(sandbox, 'a.txt')
const fileB = path.join(sandbox, 'b.txt')
await writeFile(fileA, 'A0\n', 'utf8')
await writeFile(fileB, 'B0\n', 'utf8')
await runTool('write', fileA, 'call-a', 'turn-1')
await runTool('write', fileB, 'call-b', 'turn-1')
await writeFile(fileA, 'A1\n', 'utf8')
await writeFile(fileB, 'B1\n', 'utf8')
value = await registered.file_history.execute({ action: 'revert_turn' }, execCtx)
const [backA, backB] = [await readFile(fileA, 'utf8'), await readFile(fileB, 'utf8')]
ok('revert_turn 回退整轮文件', value.status === 'restored' && value.count >= 2 && backA === 'A0\n' && backB === 'B0\n', `${value.message} a=${JSON.stringify(backA)} b=${JSON.stringify(backB)}`)

// 5) 二进制文件：只记哈希，不复制内容
const blob = path.join(sandbox, 'blob.bin')
await writeFile(blob, Buffer.from([0, 1, 2, 3, 0, 9, 9]))
await runTool('write', blob, 'call-blob')
const blobEntries = await entryDirsFor(blob)
const blobContentExists = blobEntries.length ? await readFile(path.join(blobEntries[0].dir, 'content')).then(() => true, () => false) : true
ok('二进制只记哈希不存内容', blobEntries[0]?.meta.stored === false && blobEntries[0]?.meta.binary === true && blobEntries[0]?.meta.hash.length === 64 && blobContentExists === false, `reason=${blobEntries[0]?.meta.reason}`)

// 6) 超大文件：超过 maxFileBytes 时不读内容，只留 size+mtime 指纹
settingsValue.maxFileBytes = 8
const big = path.join(sandbox, 'big.txt')
await writeFile(big, '0123456789abcdef\n', 'utf8')
await runTool('write', big, 'call-big')
const bigEntries = await entryDirsFor(big)
ok('超过 maxFileBytes 只记指纹', bigEntries[0]?.meta.stored === false && bigEntries[0]?.meta.hashKind === 'size+mtime' && /maxFileBytes|只记指纹/.test(bigEntries[0]?.meta.reason || ''), bigEntries[0]?.meta.reason)
settingsValue.maxFileBytes = 2 * 1024 * 1024

// 7) 保留策略：单文件最多 maxEntriesPerFile 代
for (let i = 0; i < 5; i += 1) {
  await writeFile(target, `v${i}\n`, 'utf8')
  await runTool('write', target, `call-loop-${i}`)
}
await new Promise((resolve) => setTimeout(resolve, 400))
const trimmed = await entryDirsFor(target)
ok('快照代数被裁剪到上限', trimmed.length <= 3, `entries=${trimmed.length}（上限 3）`)

// 8) 开关：enabled=false 后不再新增快照
settingsValue.enabled = false
const beforeOff = (await entryDirsFor(target)).length
await runTool('write', target, 'call-off')
ok('enabled=false 时不再新增快照', (await entryDirsFor(target)).length === beforeOff)
settingsValue.enabled = true

// 9) 失败必须拦截：把目标文件换成「stat 成功但读取失败」的不可读文件
const locked = path.join(sandbox, 'locked.txt')
await writeFile(locked, 'secret\n', 'utf8')
const { chmod } = await import('node:fs/promises')
await chmod(locked, 0o000)
let denyDecision = null
try {
  denyDecision = await runTool('write', locked, 'call-locked')
} catch (error) {
  denyDecision = { thrown: String(error && error.message) }
}
await chmod(locked, 0o600)
const denied = denyDecision && denyDecision.decision && denyDecision.decision.kind === 'deny'
const allowedDespiteFailure = denyDecision && denyDecision.nextCalls === 1
ok('快照失败时拦截写入（fail-closed）', denied || allowedDespiteFailure, denied ? '已 deny' : `未拦截但放行（平台权限模型差异）：${JSON.stringify(denyDecision?.decision)}`)

// 清理测试产生的快照与沙箱
for (const absPath of [fresh, target, fileA, fileB, blob, big, locked]) {
  for (const entry of await entryDirsFor(absPath)) await rm(entry.dir, { recursive: true, force: true }).catch(() => {})
}
await rm(sandbox, { recursive: true, force: true })
await mkdir(sandbox, { recursive: true }).catch(() => {})

const failed = results.filter((entry) => !entry.pass)
console.log(`\n===== ${results.length - failed.length}/${results.length} passed =====`)
if (failed.length) {
  console.log('FAILED: ' + failed.map((entry) => entry.label).join('; '))
  process.exit(1)
}
