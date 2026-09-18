// dsh-file-history 离线自测：用假 ctx/exec 直接驱动**已安装的**插件副本（不经过 harness 进程）。
// 覆盖：宿主加载路径与 schema 契约、项目内备份落点与命名、sidecar/状态标志/manifest、5 代保留、
//       file_history 四个动作、新建不备份、子目录镜像、项目外兜底、只读大文件指纹、开关、系统提示公告。
//
// 注意：这里用的是替身解析，只能验证到「宿主调用约定」这一层；真依赖（schemastery / timer）
// 的契约由 host-contract-check.mjs 在 profile 内验证。

import { mkdtemp, writeFile, readFile, readdir, mkdir, rm, stat } from 'node:fs/promises'
import { realpathSync } from 'node:fs'
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
ok('模块导出 apply/backupFileName/backupRootFor', typeof mod.apply === 'function' && typeof mod.backupFileName === 'function')
ok('项目内备份目录名为 .dsh-backup', mod.BACKUP_DIR_NAME === '.dsh-backup' && mod.backupRootFor('C:/proj') === path.join(path.resolve('C:/proj'), '.dsh-backup'))
ok('命名＝源文件名+时间戳+原扩展名', mod.backupFileName('app.ts', new Date(2026, 8, 17, 9, 55, 0)) === 'app.20260917-095500.ts')

const registered = {}
const listeners = {}
const promptSections = []
let capturedRoute = null
let capturedSchema
let capturedNs
// ── 用假 http 请求/响应驱动宿主 RPC 路由（右上角状态芯片就是调它） ──
function stripHtml(value) {
  return String(value || '').replace(/<[^>]*>/g, '')
}
async function callRoute(method, args) {
  if (!capturedRoute) return { ok: false, reason: 'route-not-registered' }
  const req = {
    method: 'POST',
    async *[Symbol.asyncIterator]() {
      yield Buffer.from(JSON.stringify({ method, args }))
    },
  }
  const chunks = []
  const res = {
    writeHead(code, headers) { this.code = code; this.headers = headers },
    end(text) { chunks.push(text) },
  }
  await capturedRoute.handler(req, res)
  return { httpStatus: res.code, ...JSON.parse(chunks.join('')) }
}
// 复刻宿主的调用约定：dsh-settings 的 resolve() 是 `schema(mergeLayers(base, section))`——
// 把合并后的配置对象**当参数调用 schema**。所以这里把 schema 记下来并真的调用一次，
// 这样「schema 必须是一个可调用、能解析默认值的 schemastery Schema」这条契约就能被测试覆盖到。
/** 宿主 agents 服务的替身：按会话 id 返回当前会话头（项目创建后会被赋值）。 */
let routeHeader
const ctx = {
  settings: {
    register: (ns, schema, options) => {
      capturedNs = ns
      capturedSchema = schema
      // 复刻宿主：用户段落 + schema 解析。update 是合并，mutate 是按路径编辑（unset 才是删除）。
      const userSection = {}
      const applyOps = (ops) => {
        for (const op of ops) {
          const path = Array.isArray(op.path) ? op.path.slice() : []
          let cursor = userSection
          for (let i = 0; i < path.length - 1; i += 1) {
            const segment = path[i]
            if (typeof cursor[segment] !== 'object' || cursor[segment] === null) cursor[segment] = {}
            cursor = cursor[segment]
          }
          const last = path[path.length - 1]
          if (op.op === 'set') cursor[last] = op.value
          else if (op.op === 'unset') delete cursor[last]
        }
      }
      const resolve = () => schema(JSON.parse(JSON.stringify(userSection)))
      const scope = {
        get: () => resolve(),
        watch: () => () => {},
        update: async (patch) => { Object.assign(userSection, patch) },
        mutate: async (_ns, ops) => { applyOps(ops) },
        replace: async (section) => {
          for (const key of Object.keys(userSection)) delete userSection[key]
          Object.assign(userSection, section)
        },
      }
      // 暴露给自测，用来在测试里改设置（走与宿主相同的路径）。
      ctx.settings.register.__scope = scope
      // 宿主 SettingsProvider 上直接有 update/mutate/replace：插件用的是这一层。
      ctx.settings.update = (patch) => scope.update(patch)
      ctx.settings.mutate = (ns, ops) => scope.mutate(ns, ops)
      ctx.settings.replace = (ns, section) => scope.replace(section)
      return scope
    },
  },
  tools: { register: (definition) => { registered[definition.name] = definition } },
  on: (event, handler) => { listeners[event] = handler },
  get: (key) => {
    if (key === 'systemPrompt') return { section: (section) => promptSections.push(section) }
    // 宿主侧服务：agents（会话→项目目录）、webServer（注册 RPC 路由）
    if (key === 'agents') return { get: (sessionId) => (routeHeader && sessionId === routeHeader.id ? { session: { header: routeHeader } } : undefined) }
    if (key === 'webServer') return { register: (route) => { capturedRoute = route; return () => {} } }
    return undefined
  },
  // timer 服务混入的 ctx.timeout（取代已 deprecated 的 ctx.setTimeout）
  timeout: (fn, ms) => setTimeout(fn, Math.min(ms || 0, 5)),
  effect: (dispose) => dispose,
  logger: { debug: () => {} },
}
let applyError
try {
  mod.apply(ctx, {})
} catch (error) {
  // 宿主加载插件时就是在这里炸的：apply() 内的 settings.register 会调用 schema。
  // 把异常记录成断言失败而不是让整个自测崩掉，改动带来这类回归时能一眼看出原因。
  applyError = error
}

// 设置变更助手：走宿主真实路径（update 合并 / mutate 路径编辑）。
const updateSettings = (patch) => ctx.settings.register.__scope.update(patch)
const setPath = (path, value) => ctx.settings.register.__scope.mutate('file-history', [{ op: 'set', path, value }])
const unsetPath = (path) => ctx.settings.register.__scope.mutate('file-history', [{ op: 'unset', path }])
ok('apply() 不抛异常（宿主加载路径）', !applyError, applyError ? `${applyError.constructor.name}: ${applyError.message}` : '')
ok(
  '注入声明包含 tools/settings/timer/agents',
  Array.isArray(mod.inject) && ['tools', 'settings', 'timer', 'agents'].every((name) => mod.inject.includes(name)),
  JSON.stringify(mod.inject),
)
ok('注册了客户端面板 RPC 路由', Boolean(capturedRoute) && capturedRoute.path === '/dsh-file-history/api', capturedRoute && capturedRoute.path)
ok('设置命名空间注册为 file-history', capturedNs === 'file-history', String(capturedNs))
ok(
  'schema 是遵循宿主约定的可调用 Schema（本 bug 的回归测试）',
  typeof capturedSchema === 'function' && typeof mod.fileHistorySettingsSchema === 'function' && typeof mod.fileHistorySettingsSchema.default === 'function',
  `typeof schema=${typeof capturedSchema}`,
)
const resolvedDefaults = typeof capturedSchema === 'function' ? capturedSchema({}) : {}
ok(
  'schema 能解析出全部默认值',
  resolvedDefaults.enabled === true && resolvedDefaults.maxGenerations === 5 && resolvedDefaults.maxFileBytes === 2 * 1024 * 1024 && resolvedDefaults.gitignoreBackups === true,
  JSON.stringify(resolvedDefaults),
)
ok('注册了 tools/pre-execute 监听', typeof listeners['tools/pre-execute'] === 'function')
ok('注册了 file_history 工具', Boolean(registered.file_history))
ok('注册了系统提示段（告知 agent 备份系统存在）', promptSections.length === 1 && promptSections[0].name === 'file-history:usage')

// ── 测试项目 ──
const project = await mkdtemp(path.join(tmpdir(), 'fh-proj-'))
const backupRoot = mod.backupRootFor(project)
const metaDir = mod.metaDirFor(project)
const outsideDir = await mkdtemp(path.join(tmpdir(), 'fh-outside-'))

const header = { id: 'session-selftest', cwd: project, title: 'self test' }
routeHeader = header
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
// mkdtemp 在 Windows 上可能返回 8.3 短路径（TWINBL~1），插件内部用的是长路径；比较前统一成长路径。
const norm = (value) => {
  if (!value) return ''
  const resolved = path.resolve(String(value))
  try {
    return realpathSync.native(resolved).toLowerCase()
  } catch {
    return resolved.toLowerCase()
  }
}
const backupsFor = async (absPath) => {
  const files = await readdir(metaDir).catch(() => [])
  const found = []
  for (const name of files) {
    if (!name.endsWith('.json') || name === 'status.json') continue
    try {
      const meta = JSON.parse(await readFile(path.join(metaDir, name), 'utf8'))
      if (meta.originalPath === absPath) found.push(meta)
    } catch {
      /* 跳过坏 sidecar */
    }
  }
  return found.sort((a, b) => String(b.backupName).localeCompare(String(a.backupName)))
}
/** 在兜底目录里找某个源文件的备份元数据。 */
const findFallbackMeta = async (absPath) => {
  let workspaces
  try {
    workspaces = await readdir(mod.HISTORY_DIR, { withFileTypes: true })
  } catch {
    return undefined
  }
  for (const workspace of workspaces) {
    if (!workspace.isDirectory() || workspace.name.startsWith('_')) continue
    const sigs = await readdir(path.join(mod.HISTORY_DIR, workspace.name), { withFileTypes: true }).catch(() => [])
    for (const sig of sigs) {
      if (!sig.isDirectory()) continue
      const ids = await readdir(path.join(mod.HISTORY_DIR, workspace.name, sig.name)).catch(() => [])
      for (const id of ids) {
        const metaPath = path.join(mod.HISTORY_DIR, workspace.name, sig.name, id, 'meta.json')
        try {
          const meta = JSON.parse(await readFile(metaPath, 'utf8'))
          if (meta.originalPath === absPath) return { ...meta, dir: path.dirname(metaPath) }
        } catch {
          /* 跳过 */
        }
      }
    }
  }
  return undefined
}

// 1) 新建文件：不备份
const fresh = path.join(project, 'brand-new.txt')
let outcome = await runTool('write', fresh, 'call-new')
ok('新建文件放行且不备份', outcome.nextCalls === 1 && (await backupsFor(fresh)).length === 0)

// 2) 覆盖已存在文件：备份进项目 .dsh-backup，命名与内容正确
const target = path.join(project, 'demo.txt')
await writeFile(target, 'line1\nline2\nline3\n', 'utf8')
outcome = await runTool('write', target, 'call-overwrite')
let metas = await backupsFor(target)
ok('覆盖已存在文件放行且备份', outcome.nextCalls === 1 && metas.length === 1, `backups=${metas.length}`)
const first = metas[0]
ok('备份落在 <项目根>/.dsh-backup/<相对路径>/ 下', first && path.dirname(first.backupPath) === backupRoot, first && first.backupPath)
ok('备份名＝源文件名+时间戳', first && /^demo\.\d{8}-\d{6}\.txt$/.test(first.backupName), first && first.backupName)
ok('备份内容是改前原文（逐字节）', (await readFile(first.backupPath, 'utf8')) === 'line1\nline2\nline3\n')
ok('sidecar 元数据在 _dsh-file-history 下', (await stat(path.join(metaDir, `${first.backupName}.json`))).isFile())
const status = JSON.parse(await readFile(path.join(metaDir, 'status.json'), 'utf8'))
ok('状态标志 status.json 记录运行状况', status.status === 'ok' && status.snapshots >= 1 && Boolean(status.lastBackup), JSON.stringify({ snapshots: status.snapshots, at: status.at }))
const manifestLines = (await readFile(path.join(metaDir, 'manifest.jsonl'), 'utf8')).trim().split('\n')
ok('manifest.jsonl 追加了审计行', manifestLines.length >= 1 && JSON.parse(manifestLines[0]).kind === 'snapshot')

// 3) 子目录镜像
const nested = path.join(project, 'src', 'lib', 'nested.ts')
await mkdir(path.dirname(nested), { recursive: true })
await writeFile(nested, 'export const v = 0\n', 'utf8')
await runTool('edit', nested, 'call-nested')
const nestedMeta = (await backupsFor(nested))[0]
ok('子目录按源路径镜像', nestedMeta && path.relative(backupRoot, nestedMeta.backupPath) === path.join('src', 'lib', nestedMeta.backupName), nestedMeta && path.relative(backupRoot, nestedMeta.backupPath))

// 4) file_history：list / show / restore
let value = await registered.file_history.execute({ action: 'list', scope: 'session' }, execCtx)
ok('list 命中备份并给出目录与状态标志', value.count >= 2 && value.message.includes(backupRoot) && value.message.includes('status.json'))

await writeFile(target, 'line1\nCHANGED\nline3\nline9\n', 'utf8')
value = await registered.file_history.execute({ action: 'show', path: target }, execCtx)
ok('show 给出 -改前/+现在 的 diff', value.message.includes('- line2') && value.message.includes('+ CHANGED'))

value = await registered.file_history.execute({ action: 'restore', path: target }, execCtx)
ok('restore 还原为改前内容', (await readFile(target, 'utf8')) === 'line1\nline2\nline3\n', value.status)
const statusAfterRestore = JSON.parse(await readFile(path.join(metaDir, 'status.json'), 'utf8'))
ok('还原也刷新状态标志与 manifest', Boolean(statusAfterRestore.lastRestore) && (await readFile(path.join(metaDir, 'manifest.jsonl'), 'utf8')).includes('"kind":"restore"'))

// 5) revert_turn：同一条助手消息内改两个文件（同一 rootCallId）
const fileA = path.join(project, 'a.txt')
const fileB = path.join(project, 'b.txt')
await writeFile(fileA, 'A0\n', 'utf8')
await writeFile(fileB, 'B0\n', 'utf8')
await runTool('write', fileA, 'call-a', 'turn-1')
await runTool('write', fileB, 'call-b', 'turn-1')
await writeFile(fileA, 'A1\n', 'utf8')
await writeFile(fileB, 'B1\n', 'utf8')
value = await registered.file_history.execute({ action: 'revert_turn' }, execCtx)
ok('revert_turn 回退整轮文件', value.status === 'restored' && value.count >= 2 && (await readFile(fileA, 'utf8')) === 'A0\n' && (await readFile(fileB, 'utf8')) === 'B0\n', value.message)

// 6) 只保留最近 5 轮：连改 8 次后只剩 5 份
const loop = path.join(project, 'loop.txt')
await writeFile(loop, 'gen0\n', 'utf8')
for (let i = 1; i <= 8; i += 1) {
  await runTool('write', loop, `call-loop-${i}`)
  await writeFile(loop, `gen${i}\n`, 'utf8')
}
const loopBackups = await backupsFor(loop)
ok('每个源文件只保留最近 5 轮', loopBackups.length === 5, `backups=${loopBackups.length}`)
const remaining = await Promise.all(loopBackups.map((meta) => readFile(meta.backupPath, 'utf8').then((text) => text.trim())))
// 每次覆盖前存的是「当时的当前内容」：8 次覆盖依次存下 gen0..gen7，只留最近 5 代 = gen3..gen7。
ok('保留的是最近 5 代内容', JSON.stringify(remaining.sort()) === JSON.stringify(['gen3', 'gen4', 'gen5', 'gen6', 'gen7']), JSON.stringify(remaining))

// 7) 项目外文件走兜底目录，不污染外部目录
const outside = path.join(outsideDir, 'outside.txt')
await writeFile(outside, 'outside v0\n', 'utf8')
await runTool('write', outside, 'call-outside')
const outsideBackupDirs = await readdir(outsideDir)
ok('项目外文件不写进外部目录', !outsideBackupDirs.includes('.dsh-backup'), JSON.stringify(outsideBackupDirs))
const fallbackMeta = await findFallbackMeta(outside)
ok('项目外文件落到兜底目录且带元数据', Boolean(fallbackMeta) && fallbackMeta.stored === true, fallbackMeta && fallbackMeta.backupPath)
value = await registered.file_history.execute({ action: 'list', scope: 'session' }, execCtx)
ok('项目外文件的备份仍能被 list 看到', value.entries.some((entry) => entry.path === outside), `count=${value.count}`)
ok('项目外文件也能被 restore 还原', (await registered.file_history.execute({ action: 'restore', path: outside }, execCtx)).status === 'restored')

// 8) 大文件只记指纹
await updateSettings({ maxFileBytes: 8 })
const big = path.join(project, 'big.txt')
await writeFile(big, '0123456789abcdef\n', 'utf8')
await runTool('write', big, 'call-big')
const bigMeta = (await backupsFor(big))[0]
ok('超过 maxFileBytes 只记指纹且无内容副本', bigMeta && bigMeta.stored === false && bigMeta.hashKind === 'size+mtime' && !(await stat(bigMeta.backupPath).then(() => true, () => false)), bigMeta && bigMeta.reason)
ok('不可还原的条目不会谎报可还原', bigMeta && value.entries.every((entry) => entry.path !== big || entry.restorable === false))
await updateSettings({ maxFileBytes: 2 * 1024 * 1024 })

// 9) 备份系统不备份自己
const selfFile = path.join(backupRoot, 'self.txt')
await writeFile(selfFile, 'x\n', 'utf8')
outcome = await runTool('write', selfFile, 'call-self')
ok('.dsh-backup 内的文件不会被再次备份', outcome.nextCalls === 1 && (await backupsFor(selfFile)).length === 0)

// 10) 开关关闭后不再备份
await setPath(['enabled'], false)
const beforeOff = (await backupsFor(target)).length
await runTool('write', target, 'call-off')
ok('enabled=false 时不再备份', (await backupsFor(target)).length === beforeOff)
await setPath(['enabled'], true)

// 10.5) git 卫生：自动把 .dsh-backup/ 登记进 .gitignore，且不重写已有内容
const gitProject = await mkdtemp(path.join(tmpdir(), 'fh-git-'))
await mkdir(path.join(gitProject, '.git'), { recursive: true })
await writeFile(path.join(gitProject, '.gitignore'), 'node_modules/\n', 'utf8')
const gitFile = path.join(gitProject, 'code.js')
await writeFile(gitFile, 'const a = 1\n', 'utf8')
const gitHeader = { id: 'session-git', cwd: gitProject, title: 'git test' }
await listeners['tools/pre-execute'](
  { name: 'write', callId: 'c-git', rootCallId: 'c-git', arguments: { file_path: gitFile }, agent: { session: { header: gitHeader } }, signal: { throwIfAborted: () => {} } },
  async () => ({ kind: 'allow' }),
)
const gitignoreText = await readFile(path.join(gitProject, '.gitignore'), 'utf8')
ok('自动把 .dsh-backup/ 写进 .gitignore 且保留原内容', gitignoreText.includes('node_modules/') && gitignoreText.includes('.dsh-backup/'), JSON.stringify(gitignoreText))
await listeners['tools/pre-execute'](
  { name: 'write', callId: 'c-git2', rootCallId: 'c-git2', arguments: { file_path: gitFile }, agent: { session: { header: gitHeader } }, signal: { throwIfAborted: () => {} } },
  async () => ({ kind: 'allow' }),
)
const gitignoreAgain = await readFile(path.join(gitProject, '.gitignore'), 'utf8')
ok('.gitignore 不会被重复追加', (gitignoreAgain.match(/\.dsh-backup\//g) || []).length === 1)
await setPath(['gitignoreBackups'], false)
const gitFile2 = path.join(gitProject, 'code2.js')
await writeFile(gitFile2, 'const b = 2\n', 'utf8')
await writeFile(path.join(gitProject, '.gitignore'), 'node_modules/\n', 'utf8')
await listeners['tools/pre-execute'](
  { name: 'write', callId: 'c-git3', rootCallId: 'c-git3', arguments: { file_path: gitFile2 }, agent: { session: { header: gitHeader } }, signal: { throwIfAborted: () => {} } },
  async () => ({ kind: 'allow' }),
)
ok('gitignoreBackups=false 时不改动 .gitignore', (await readFile(path.join(gitProject, '.gitignore'), 'utf8')) === 'node_modules/\n')
await setPath(['gitignoreBackups'], true)
await rm(gitProject, { recursive: true, force: true }).catch(() => {})

// 10.6) 嵌套仓库：工作区是仓库子目录时，条目要带相对路径写到「仓库根」的 .gitignore
const outerRepo = await mkdtemp(path.join(tmpdir(), 'fh-outer-'))
const innerWorkspace = path.join(outerRepo, 'backup')
await mkdir(path.join(outerRepo, '.git'), { recursive: true })
await mkdir(innerWorkspace, { recursive: true })
await writeFile(path.join(outerRepo, '.gitignore'), '# 运行时目录\napi/\n', 'utf8')
const innerFile = path.join(innerWorkspace, 'code.py')
await writeFile(innerFile, 'x = 1\n', 'utf8')
const innerHeader = { id: 'session-inner', cwd: innerWorkspace, title: 'nested test' }
await listeners['tools/pre-execute'](
  { name: 'write', callId: 'c-inner', rootCallId: 'c-inner', arguments: { file_path: innerFile }, agent: { session: { header: innerHeader } }, signal: { throwIfAborted: () => {} } },
  async () => ({ kind: 'allow' }),
)
const outerGitignore = await readFile(path.join(outerRepo, '.gitignore'), 'utf8')
ok('嵌套仓库：条目写到仓库根且带相对路径', outerGitignore.includes('/backup/.dsh-backup/') && outerGitignore.includes('api/'), JSON.stringify(outerGitignore))
ok('嵌套仓库：不往子目录塞 .gitignore', !(await stat(path.join(innerWorkspace, '.gitignore')).then(() => true, () => false)))
await rm(outerRepo, { recursive: true, force: true }).catch(() => {})

// 11) 系统提示公告内容包含目录与工具用法
const announcement = promptSections[0].text({ agent: { session: { header } } })
const announcedPaths = [...announcement.matchAll(/`([^`]+)`/g)].map((match) => norm(match[1]))
ok(
  '系统提示告知备份目录与恢复方式',
  announcedPaths.includes(norm(backupRoot)) &&
    announcement.includes('file_history') &&
    announcement.includes('action="restore"') &&
    announcement.includes('action="revert_turn"') &&
    announcement.includes('status.json'),
  `announced=${announcedPaths.length} paths`,
)
ok('系统提示写明每文件保留代数', announcement.includes('最近几代') || announcement.includes('保留最近'))
await setPath(['announceInPrompt'], false)
ok('announceInPrompt=false 时不注入该段', promptSections[0].text({ agent: { session: { header } } }) === '')
await setPath(['announceInPrompt'], true)

// 12) 右上角状态芯片的 RPC：state 要给出项目、状态标志、统计与实时流水
const stateResponse = await callRoute('state', { sessionId: header.id })
ok(
  'RPC state 返回当前项目与状态标志',
  stateResponse.ok === true && norm(stateResponse.projectDir) === norm(project) && stateResponse.statusPath.endsWith('status.json'),
  `${stateResponse.ok} / ${stateResponse.projectName}`,
)
ok('RPC state 含备份统计与代数设置', stateResponse.stat.count >= 1 && stateResponse.settings.maxGenerations === 5, JSON.stringify(stateResponse.stat))
// 芯片上的数字用 stat.bytes（当前占用）：必须等于现存备份文件大小之和，
// 「随清理降下来」才成立（回归点：曾经误用历史累计次数 snapshots）。
const sidecarBytes = await Promise.all(
  (await readdir(metaDir))
    .filter((name) => name.endsWith('.json') && name !== 'status.json')
    .map((name) => readFile(path.join(metaDir, name), 'utf8').then((text) => Number(JSON.parse(text).size) || 0, () => 0)),
)
const sidecarSum = sidecarBytes.reduce((sum, value) => sum + value, 0)
ok(
  'RPC stat.bytes ＝ 现存备份大小之和（可用于「当前占用」口径）',
  stateResponse.stat.bytes === sidecarSum && sidecarSum > 0 && sidecarSum !== (stateResponse.status ? stateResponse.status.snapshots : -1),
  `bytes=${stateResponse.stat.bytes} sidecarSum=${sidecarSum} snapshots=${stateResponse.status && stateResponse.status.snapshots}`,
)
ok(
  'RPC state 含实时流水（时间/动作/文件）',
  Array.isArray(stateResponse.events) && stateResponse.events.length >= 1 && Boolean(stateResponse.events[0].kind) && Boolean(stateResponse.events[0].file),
  JSON.stringify(stateResponse.events[0] || {}),
)

// 12.5) 项目级开关：只影响当前项目，且能被「改回跟随全局默认」
const key = mod.projectKeyOf(project)
ok('默认是继承全局（无项目覆盖）', stateResponse.settings.scope === 'inherit' && stateResponse.settings.globalEnabled === true && stateResponse.settings.enabled === true, JSON.stringify(stateResponse.settings))
const offProject = await callRoute('set-enabled', { sessionId: header.id, enabled: false, scope: 'project' })
ok(
  '关闭只写本项目覆盖，不动全局默认',
  offProject.ok === true && offProject.scope === 'project' && offProject.enabled === false && offProject.globalEnabled === true,
  JSON.stringify(offProject),
)
ok('覆盖键＝项目目录（小写规范化）', Boolean(key) && key === mod.projectKeyOf(project), String(key))
const offState = await callRoute('state', { sessionId: header.id })
ok('本项目已经关掉（生效值 false）', offState.settings.enabled === false && offState.settings.scope === 'project')
// 关掉本项目后，pre-execute 不该再备份（但也不能拦下写入）
const backupsBeforeOff = (await backupsFor(target)).length
outcome = await runTool('write', target, 'call-project-off')
ok('本项目关闭时不再备份且照常放行', outcome.nextCalls === 1 && (await backupsFor(target)).length === backupsBeforeOff)
// 全局默认关掉，但本项目有覆盖 → 本项目仍然保持自己的设置
const globalOff = await callRoute('set-enabled', { sessionId: header.id, enabled: false, scope: 'global' })
ok('全局默认可单独改写', globalOff.ok === true && globalOff.globalEnabled === false, JSON.stringify(globalOff))
const stillOff = await callRoute('state', { sessionId: header.id })
ok('项目覆盖优先于全局默认', stillOff.settings.scope === 'project' && stillOff.settings.enabled === false)
// 改回跟随全局默认
const reset = await callRoute('reset-project', { sessionId: header.id })
ok('reset-project 删除项目覆盖', reset.ok === true && reset.scope === 'inherit', JSON.stringify(reset))
const inheritOff = await callRoute('state', { sessionId: header.id })
ok('恢复继承后跟随全局默认（全局关 → 本项目也关）', inheritOff.settings.scope === 'inherit' && inheritOff.settings.enabled === false, JSON.stringify(inheritOff.settings))
// 恢复默认：全局开、无项目覆盖
await callRoute('set-enabled', { sessionId: header.id, enabled: true, scope: 'global' })
const restored = await callRoute('state', { sessionId: header.id })
ok('回到全部启用', restored.settings.enabled === true && restored.settings.scope === 'inherit')

const badRoute = await callRoute('set-enabled', { enabled: 'yes' })
ok('RPC 参数非法时返回错误而不是抛异常', badRoute.ok === false && badRoute.reason === 'bad-args', JSON.stringify(badRoute))
const getOnly = await capturedRoute.handler({ method: 'GET', async *[Symbol.asyncIterator]() {} }, { writeHead() {}, end() {} })
ok('RPC 路由只接受 POST', getOnly === undefined)

// 清理
await rm(project, { recursive: true, force: true }).catch(() => {})
await rm(outsideDir, { recursive: true, force: true }).catch(() => {})
for (const meta of await (async () => {
  const dir = path.join(mod.HISTORY_DIR, 'unknown')
  return []
})()) void meta

const failed = results.filter((entry) => !entry.pass)
console.log(`\n===== ${results.length - failed.length}/${results.length} passed =====`)
if (failed.length) {
  console.log('FAILED: ' + failed.map((entry) => entry.label).join('; '))
  process.exit(1)
}
