// dsh-cleaner — Host half (static / composition plugin)
//
// dsh 原生没有删除会话/工作区的入口。本插件在 dsh 进程内补上它：
//   1. 工作区删除：调用产品自己的 workspaceRegistry.delete(id)（与
//      @deepseek-ai/dsh-api-workspace-controller 的 workspace/delete 同一条
//      产品级路径），登记变更经由产品自身的变更流广播 → 侧栏自动刷新；
//   2. 会话删除：先 workspaceRegistry.get(ws).detachSession(sessionId)
//      （产品原生的登记摘除，走 storage 写链），再把会话目录从
//      DSH_HOME/sessions/<工作区目录>/ 移入 DSH_HOME/trash/session-cleaner/
//      （移动而非硬删，可恢复）；
//   3. 孤儿会话清理：sessions/ 下未被任何工作区登记的目录（多为 api-* 任务
//      会话残留），同样移入回收目录；
//   4. 回收目录支持列表与恢复（恢复时经 attachSession 校验 cwd 后重新登记）。
//
// 所有操作经由本插件自己的 JSON API（POST /dsh-cleaner/api，body
// { method, args }），客户端半部用 fetch 调用——与 dsh-time-stamp/netmon
// 同一条经过验证的第三方通道，无需 typert/zod。
//
// 安全边界：
//   · 正在被任何窗口使用的会话（agents 里有活体）拒绝删除；
//   · 删除一律进回收目录，绝不直接 unlink；恢复经 attachSession 校验。
import { Service } from '@deepseek-ai/cordis'
import { readdirSync, statSync, mkdirSync, existsSync, renameSync, rmSync, readFileSync, writeFileSync } from 'node:fs'
import { join, basename, dirname } from 'node:path'
import { homedir, tmpdir } from 'node:os'

export const ROUTE_PATH = '/dsh-cleaner/api'

/** DSH 主目录（与启动器/桥同一约定：DSH_HOME 优先，缺省 ~/.dsh）。 */
function dshHome() {
  const env = process.env.DSH_HOME
  return env && env.trim() !== '' ? env.trim() : join(homedir(), '.dsh')
}

export class CleanerService extends Service {
  static inject = ['workspaceRegistry', 'webServer', 'agents']

  constructor(ctx) {
    super(ctx, 'cleaner')
  }

  async [Service.init]() {
    this.ctx.effect(() => this.ctx.webServer.register({
      kind: 'exact',
      path: ROUTE_PATH,
      handler: (req, res) => this.handleApi(req, res),
    }))
  }

  // ── 路径辅助 ─────────────────────────────────────────────────────────

  sessionsRoot() {
    return join(dshHome(), 'sessions')
  }

  trashRoot() {
    return join(dshHome(), 'trash', 'session-cleaner')
  }

  /** 读取会话投影缓存（标题/统计），失败时返回空表——面板降级为只显示 id。 */
  readProjections() {
    try {
      const raw = readFileSync(join(dshHome(), 'storages', 'session_projcache.json'), 'utf8')
      const parsed = JSON.parse(raw)
      return (parsed && parsed.tables && parsed.tables.sessions) || {}
    } catch {
      return {}
    }
  }

  /** 一个会话 id 在磁盘上的全部目录（正常只有一个；历史残留可能多处）。 */
  sessionDirs(sessionId) {
    const root = this.sessionsRoot()
    const found = []
    if (!existsSync(root)) return found
    for (const wsDir of readdirSync(root, { withFileTypes: true })) {
      if (!wsDir.isDirectory()) continue
      const candidate = join(root, wsDir.name, sessionId)
      if (existsSync(candidate)) found.push(candidate)
    }
    return found
  }

  /** 汇总一个会话目录的大小与最后修改时间。 */
  dirStats(dir) {
    let bytes = 0
    let mtime = 0
    const walk = (p) => {
      for (const entry of readdirSync(p, { withFileTypes: true })) {
        const full = join(p, entry.name)
        if (entry.isDirectory()) walk(full)
        else {
          try {
            const st = statSync(full)
            bytes += st.size
            if (st.mtimeMs > mtime) mtime = st.mtimeMs
          } catch { }
        }
      }
    }
    try { walk(dir) } catch { }
    return { bytes, mtime }
  }

  /** 回收目录里还没有占用过的名字。 */
  freshTrashName(sessionId) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    const base = `${stamp}_${sessionId}`
    let name = base
    let n = 1
    while (existsSync(join(this.trashRoot(), name))) name = `${base}_${n++}`
    return name
  }

  /** 把一个会话目录移入回收目录，并写入恢复清单。 */
  moveToTrash(dir, meta) {
    const trashRoot = this.trashRoot()
    mkdirSync(trashRoot, { recursive: true })
    const name = this.freshTrashName(basename(dir))
    const entryDir = join(trashRoot, name)
    mkdirSync(entryDir, { recursive: true })
    renameSync(dir, join(entryDir, basename(dir)))
    writeFileSync(join(entryDir, 'manifest.json'), JSON.stringify({
      ...meta,
      fromDir: dirname(dir),
      dirName: basename(dir),
      when: new Date().toISOString(),
    }, null, 2))
    return { name, bytes: this.dirStats(entryDir).bytes }
  }

  /** 会话正在被某个窗口使用时拒绝删除（agents 里有活体即视为打开）。 */
  isOpen(sessionId) {
    try {
      return !!(this.ctx.agents && this.ctx.agents.get && this.ctx.agents.get(sessionId))
    } catch {
      return false
    }
  }

  assertNotOpen(sessionId) {
    if (this.isOpen(sessionId)) {
      throw new Error(`会话「${sessionId}」正在使用中：请先在界面里切到别的会话再删除`)
    }
  }

  /** 会话的展示信息：标题/统计来自投影缓存，体积与时间来自磁盘。 */
  sessionView(sessionId, proj, archivedSet) {
    const p = (proj && proj[sessionId]) || null
    const rows = p && p.rows ? p.rows : {}
    const identity = p && p.identity ? p.identity : {}
    const stats = rows.sessionStats && rows.sessionStats.val ? rows.sessionStats.val : {}
    const usage = rows.tokenUsage && rows.tokenUsage.val && rows.tokenUsage.val.totals
      ? rows.tokenUsage.val.totals : {}
    let bytes = 0
    let mtime = 0
    for (const dir of this.sessionDirs(sessionId)) {
      const s = this.dirStats(dir)
      bytes += s.bytes
      if (s.mtime > mtime) mtime = s.mtime
    }
    return {
      id: sessionId,
      title: rows.title && rows.title.val ? rows.title.val : null,
      bytes,
      mtime,
      turns: typeof stats.turns === 'number' ? stats.turns : null,
      lastPromptAt: typeof identity.lastPromptAt === 'number' ? identity.lastPromptAt : null,
      createdAt: typeof identity.createdAt === 'number' ? identity.createdAt : null,
      outputTokens: typeof usage.outputTokens === 'number' ? usage.outputTokens : null,
      archived: archivedSet ? archivedSet.has(sessionId) : false,
      open: this.isOpen(sessionId),
    }
  }

  /** 所有工作区的可删除视图 + 孤儿会话清单。 */
  listWorkspaces() {
    const proj = this.readProjections()
    const archivedSet = new Set((this.ctx.workspaceRegistry.archivedSessionIds || []).map(String))
    const accounted = new Set()
    const workspaces = []
    for (const w of this.ctx.workspaceRegistry.list()) {
      const id = String(w.id)
      let handle = null
      try { handle = this.ctx.workspaceRegistry.get(id) } catch { }
      const title = handle && handle.title ? handle.title : w.title
      const path = handle && handle.path ? handle.path : w.path
      const sessionIds = handle ? [...handle.sessionIds] : [...(w.sessionIds || [])]
      const sessions = sessionIds.map((sid) => {
        const key = String(sid)
        accounted.add(key)
        return this.sessionView(key, proj, archivedSet)
      })
      workspaces.push({
        id,
        title,
        path,
        sessions,
        bytes: sessions.reduce((sum, s) => sum + (s.bytes || 0), 0),
      })
    }
    // 孤儿：sessions/ 下存在目录、但不在任何工作区登记里的会话。
    const seenOrphans = new Set()
    const orphans = []
    const root = this.sessionsRoot()
    if (existsSync(root)) {
      for (const wsDir of readdirSync(root, { withFileTypes: true })) {
        if (!wsDir.isDirectory()) continue
        const sub = join(root, wsDir.name)
        for (const entry of readdirSync(sub, { withFileTypes: true })) {
          if (!entry.isDirectory()) continue
          const name = entry.name
          if (accounted.has(name) || seenOrphans.has(name)) continue
          seenOrphans.add(name)
          orphans.push(this.sessionView(name, proj, archivedSet))
        }
      }
    }
    return { workspaces, orphans }
  }

  /** 找到登记了某会话的工作区（返回 handle 或 null）。 */
  ownerHandleOf(sessionId) {
    for (const w of this.ctx.workspaceRegistry.list()) {
      let handle = null
      try { handle = this.ctx.workspaceRegistry.get(String(w.id)) } catch { continue }
      if (handle && [...handle.sessionIds].includes(sessionId)) return handle
    }
    return null
  }

  // ── 动作实现 ─────────────────────────────────────────────────────────

  async deleteSession(sessionId) {
    sessionId = String(sessionId)
    if (sessionId === '') throw new Error('缺少 sessionId')
    this.assertNotOpen(sessionId)
    const handle = this.ownerHandleOf(sessionId)
    let detached = false
    if (handle) {
      await handle.detachSession(sessionId)   // 产品原生：走 storage 写链并广播变更
      detached = true
    }
    const dirs = this.sessionDirs(sessionId)
    if (dirs.length === 0 && !detached) throw new Error(`磁盘上找不到会话「${sessionId}」的目录`)
    const moved = []
    for (const dir of dirs) {
      moved.push(this.moveToTrash(dir, {
        sessionId,
        workspaceId: handle ? String(handle.id) : null,
      }))
    }
    return { ok: true, detached, moved, freed: moved.reduce((sum, m) => sum + (m.bytes || 0), 0) }
  }

  async deleteWorkspace(workspaceId) {
    workspaceId = String(workspaceId)
    let handle = null
    try { handle = this.ctx.workspaceRegistry.get(workspaceId) } catch { }
    if (!handle) throw new Error(`工作区「${workspaceId}」不存在（可能已被删除）`)
    const sessionIds = [...handle.sessionIds]
    for (const sid of sessionIds) this.assertNotOpen(sid)
    const moved = []
    for (const sid of sessionIds) {
      for (const dir of this.sessionDirs(sid)) {
        moved.push(this.moveToTrash(dir, { sessionId: sid, workspaceId }))
      }
    }
    const deleted = await this.ctx.workspaceRegistry.delete(workspaceId)
    return {
      ok: true,
      deleted: deleted !== false,
      sessions: moved.length,
      freed: moved.reduce((sum, m) => sum + (m.bytes || 0), 0),
    }
  }

  async deleteOrphan(sessionId) {
    sessionId = String(sessionId)
    this.assertNotOpen(sessionId)
    const dirs = this.sessionDirs(sessionId)
    if (dirs.length === 0) throw new Error(`磁盘上找不到会话「${sessionId}」的目录`)
    const moved = []
    for (const dir of dirs) moved.push(this.moveToTrash(dir, { sessionId, workspaceId: null }))
    return { ok: true, moved, freed: moved.reduce((sum, m) => sum + (m.bytes || 0), 0) }
  }

  trashList() {
    const root = this.trashRoot()
    const entries = []
    if (!existsSync(root)) return { ok: true, entries }
    for (const name of readdirSync(root, { withFileTypes: true })) {
      if (!name.isDirectory()) continue
      const entryDir = join(root, name.name)
      let manifest = {}
      try { manifest = JSON.parse(readFileSync(join(entryDir, 'manifest.json'), 'utf8')) } catch { }
      const inner = join(entryDir, manifest.dirName || '')
      const stats = existsSync(inner) ? this.dirStats(inner) : { bytes: 0, mtime: 0 }
      entries.push({
        name: name.name,
        sessionId: manifest.sessionId || manifest.dirName || name.name,
        workspaceId: manifest.workspaceId || null,
        when: manifest.when || null,
        bytes: stats.bytes,
      })
    }
    entries.sort((a, b) => String(b.when || '').localeCompare(String(a.when || '')))
    return { ok: true, entries }
  }

  async restore(name) {
    name = String(name)
    const entryDir = join(this.trashRoot(), name)
    const manifestPath = join(entryDir, 'manifest.json')
    if (!existsSync(manifestPath)) throw new Error(`回收条目「${name}」不存在或没有恢复清单`)
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
    if (!manifest.dirName || !manifest.fromDir) throw new Error(`回收条目「${name}」的清单缺少原始位置`)
    const inner = join(entryDir, manifest.dirName)
    if (!existsSync(inner)) throw new Error(`回收条目「${name}」的数据目录已缺失`)
    const targetParent = join(this.sessionsRoot(), basename(manifest.fromDir))
    mkdirSync(targetParent, { recursive: true })
    const target = join(targetParent, manifest.dirName)
    if (existsSync(target)) throw new Error(`目标位置已存在同名会话目录，无法恢复：${manifest.dirName}`)
    renameSync(inner, target)
    try { rmSync(entryDir, { recursive: true, force: true }) } catch { }
    let reattached = false
    if (manifest.workspaceId) {
      try {
        const handle = this.ctx.workspaceRegistry.get(String(manifest.workspaceId))
        if (handle) {
          await handle.attachSession(String(manifest.sessionId))
          reattached = true
        }
      } catch { }
    }
    return { ok: true, target, reattached }
  }

  /** 自检：临时目录上走一遍 登记 → 出现在列表 → 删除 → 消失 的产品级路径。 */
  async selftest() {
    const dir = join(tmpdir(), 'dsh-cleaner-selftest-' + Date.now())
    mkdirSync(dir, { recursive: true })
    const handle = await this.ctx.workspaceRegistry.create(dir)
    const id = String(handle.id)
    const created = this.ctx.workspaceRegistry.list().some((w) => String(w.id) === id)
    const deleted = await this.ctx.workspaceRegistry.delete(id)
    const gone = !this.ctx.workspaceRegistry.list().some((w) => String(w.id) === id)
    try { rmSync(dir, { recursive: true, force: true }) } catch { }
    return { ok: true, created, deleted: deleted !== false, gone }
  }

  // ── HTTP 外壳（与 dsh-time-stamp 同一条经过验证的通道）───────────────

  async handleApi(req, res) {
    const send = (status, body) => {
      res.writeHead(status, { 'content-type': 'application/json; charset=utf-8' })
      res.end(JSON.stringify(body))
    }
    if (req.method !== 'POST') {
      send(405, { ok: false, reason: 'method-not-allowed' })
      return
    }
    let raw = ''
    try {
      for await (const chunk of req) raw += chunk
    } catch {
      send(400, { ok: false, reason: 'read-failed' })
      return
    }
    let request
    try {
      request = JSON.parse(raw)
    } catch {
      send(400, { ok: false, reason: 'bad-json' })
      return
    }
    const method = request && typeof request.method === 'string' ? request.method : ''
    const args = request && typeof request.args === 'object' && request.args !== null ? request.args : {}
    try {
      send(200, await this.dispatch(method, args))
    } catch (error) {
      send(200, { ok: false, reason: error instanceof Error ? error.message : String(error) })
    }
  }

  async dispatch(method, args) {
    switch (method) {
      case 'list':
        return { ok: true, ...this.listWorkspaces() }
      case 'delete-session':
        return await this.deleteSession(args.sessionId)
      case 'delete-workspace':
        return await this.deleteWorkspace(args.workspaceId)
      case 'delete-orphan':
        return await this.deleteOrphan(args.sessionId)
      case 'trash-list':
        return this.trashList()
      case 'restore':
        return await this.restore(args.name)
      case 'selftest':
        return await this.selftest()
      default:
        return { ok: false, reason: `unknown-method:${method}` }
    }
  }
}

export default CleanerService
