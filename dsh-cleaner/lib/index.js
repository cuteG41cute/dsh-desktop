// dsh-cleaner — Host half (static / composition plugin)
//
// dsh 原生没有删除会话/工作区的入口。本插件在 dsh 进程内补上它，并且
// **删除一律是"搬家"而不是"销毁"**：
//
//   1. 删除工作区（项目）= 解除与 dsh 的关联 + 整个项目文件夹原封不动搬进
//      用户文档下的「DSH Recycle Bin」：
//        · 先逐个 detachSession（产品原生登记摘除，走 storage 写链并广播变更）
//          再 workspaceRegistry.delete(id)（与官方 workspace 控制器同一条路径）；
//        · 工作区的真实项目文件夹（含里面的所有文件，逐字节保持原样）整体移动
//          到 <DSH Recycle Bin>/<时间>_workspace_<标题>/<项目文件夹名>/；
//        · 该工作区的全部会话记录一并搬到同一回收条目的 sessions/ 子目录；
//        · 回收条目内写入「恢复说明.md」与可双击运行的「恢复.ps1」。
//   2. 删除会话 = detachSession + 该会话记录目录搬进 DSH Recycle Bin；
//   3. 孤儿会话（不在任何登记里，多为 api-* 残留）同样入库；
//   4. 回收站支持列表与恢复：会话条目一键还原；工作区条目把项目文件夹与
//      会话记录都搬回原位并重新登记（恢复脚本也能离线完成同样的动作）。
//
// 回收目的地：<用户文档>/DSH Recycle Bin（可用 DSH_CLEANER_RECYCLE_BIN 覆盖）。
// 首次运行会把旧版（v1）留在 ~/.dsh/trash/session-cleaner 的条目迁入同一处。
//
// 保险（拒绝执行而不是冒险）：
//   · 工作区里还有会话被窗口打开着 → 拒绝；
//   · 项目路径是驱动器根、是用户主目录、是系统目录（Windows/Program Files/
//     ProgramData/AppData 等）→ 拒绝；
//   · 项目路径包含 DSH 主目录、回收站，或是本进程当前工作目录的祖先 → 拒绝；
//   · 名字重复导致目标已存在 → 拒绝。
//
// 回收条目结构：
//   <bin>/2026-10-08T08-30-00-000Z_workspace_deeepseek harness/
//     ├─ 恢复说明.md            ← 人读的恢复步骤
//     ├─ 恢复.ps1               ← 双击/右键运行即还原（UTF-8 BOM）
//     ├─ manifest.json          ← 机器读的原始位置与归属
//     ├─ deeepseek harness/     ← 项目文件夹原样（所有文件逐字节未改）
//     └─ sessions/              ← 该工作区的会话记录
//
// 加载契约：本模块必须 export default（cordis 加载器只接受函数或带 apply
// 方法的对象作为模块值，否则整个插件树中止加载）。
import { Service } from '@deepseek-ai/cordis'
import {
  readdirSync, statSync, mkdirSync, existsSync, renameSync, rmSync,
  readFileSync, writeFileSync, cpSync,
} from 'node:fs'
import { join, basename, dirname, parse, resolve, sep } from 'node:path'
import { homedir, tmpdir } from 'node:os'

export const ROUTE_PATH = '/dsh-cleaner/api'

/** DSH 主目录（与启动器/桥同一约定：DSH_HOME 优先，缺省 ~/.dsh）。 */
function dshHome() {
  const env = process.env.DSH_HOME
  return env && env.trim() !== '' ? env.trim() : join(homedir(), '.dsh')
}

/** 回收目的地：<用户文档>/DSH Recycle Bin（DSH_CLEANER_RECYCLE_BIN 可覆盖）。 */
export function recycleBin() {
  const env = process.env.DSH_CLEANER_RECYCLE_BIN
  if (env && env.trim() !== '') return env.trim()
  return join(homedir(), 'Documents', 'DSH Recycle Bin')
}

/** 规范化比较用路径（Windows 不区分大小写）。 */
function samePath(a, b) {
  return resolve(a).toLowerCase() === resolve(b).toLowerCase()
}

/** a 是否是 b 的祖先目录（或相等）。 */
function isAncestor(a, b) {
  const x = resolve(a).toLowerCase().replace(/[\\/]+$/, '')
  const y = resolve(b).toLowerCase().replace(/[\\/]+$/, '')
  if (x === y) return true
  return y.startsWith(x + sep) || y.startsWith(x + '/')
}

/** 目录名安全化（Windows 文件名禁用字符）。 */
function sanitizeName(name) {
  return String(name).replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/[. ]+$/, '').slice(0, 80) || 'workspace'
}

/** 跨盘移动：先 rename，失败（EXDEV）退回复制 + 删除；保留时间戳。 */
function moveDir(src, dest) {
  mkdirSync(dirname(dest), { recursive: true })
  try {
    renameSync(src, dest)
    return 'rename'
  } catch (error) {
    if (error && error.code !== 'EXDEV') throw error
    cpSync(src, dest, { recursive: true, preserveTimestamps: true, verbatimSymlinks: true })
    rmSync(src, { recursive: true, force: true })
    return 'copy'
  }
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
    this.migrateLegacyTrash()
  }

  /** 旧版（v2）把删除物放在 ~/.dsh/trash/session-cleaner；迁入 DSH Recycle Bin。 */
  migrateLegacyTrash() {
    try {
      const legacy = join(dshHome(), 'trash', 'session-cleaner')
      if (!existsSync(legacy)) return
      const bin = recycleBin()
      mkdirSync(bin, { recursive: true })
      for (const name of readdirSync(legacy, { withFileTypes: true })) {
        const from = join(legacy, name.name)
        const to = join(bin, name.name)
        if (existsSync(to)) rmSync(from, { recursive: true, force: true })
        else renameSync(from, to)
      }
      try { rmSync(join(dshHome(), 'trash'), { recursive: true, force: true }) } catch { }
    } catch { }
  }

  // ── 路径辅助 ─────────────────────────────────────────────────────────

  sessionsRoot() {
    return join(dshHome(), 'sessions')
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
    if (!sessionId || !existsSync(root)) return found
    for (const wsDir of readdirSync(root, { withFileTypes: true })) {
      if (!wsDir.isDirectory()) continue
      const candidate = join(root, wsDir.name, sessionId)
      if (existsSync(candidate)) found.push(candidate)
    }
    return found
  }

  /** 汇总一个目录的大小与最后修改时间。 */
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

  /** DSH Recycle Bin 里还没有占用过的名字。 */
  freshRecycleName(prefix) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    const base = `${stamp}_${sanitizeName(prefix)}`
    let name = base
    let n = 1
    while (existsSync(join(recycleBin(), name))) name = `${base}_${n++}`
    return name
  }

  /** 新建一个回收条目目录。 */
  newRecycleEntry(prefix) {
    const bin = recycleBin()
    mkdirSync(bin, { recursive: true })
    const name = this.freshRecycleName(prefix)
    const entryDir = join(bin, name)
    mkdirSync(entryDir, { recursive: true })
    return { name, entryDir }
  }

  /** 写入人的恢复说明（Markdown）。 */
  writeRestoreGuide(entryDir, manifest) {
    const lines = []
    lines.push('# 恢复说明（DSH Recycle Bin）')
    lines.push('')
    lines.push(`- 删除时间：${manifest.when}`)
    lines.push(`- 类型：${manifest.kind === 'workspace' ? '工作区（项目文件夹）' : '会话记录'}`)
    if (manifest.kind === 'workspace') {
      lines.push(`- 项目名称：${manifest.title || basename(manifest.projectPath || '')}`)
      lines.push(`- 项目原位置：\`${manifest.projectPath}\``)
      lines.push(`- 项目文件夹（原样保留）：\`${manifest.projectName}\`（与本文件同级）`)
    }
    if (manifest.sessionIds && manifest.sessionIds.length > 0) {
      lines.push(`- 会话记录：${manifest.sessionIds.length} 个，位于本目录 \`sessions/\``)
    }
    lines.push('')
    lines.push('## 一键恢复（推荐）')
    lines.push('')
    lines.push('1. 右键本目录里的 **`恢复.ps1`** → 「使用 PowerShell 运行」。')
    lines.push('   （若提示脚本策略限制，可在 PowerShell 里执行：`powershell -ExecutionPolicy Bypass -File .\\恢复.ps1`）')
    lines.push('2. 脚本会把项目文件夹搬回原位、会话记录搬回 `DSH_HOME/sessions/`，并打印结果。')
    lines.push('3. 打开 DeepSeek Harness，在左侧栏「添加工作区」里选择项目路径重新登记。')
    lines.push('')
    lines.push('## 手动恢复')
    lines.push('')
    if (manifest.kind === 'workspace') {
      lines.push(`1. 把本目录下的 \`${manifest.projectName}\` 整个文件夹**移动回** \`${dirname(manifest.projectPath)}\`。`)
      lines.push(`   （目标路径：\`${manifest.projectPath}\`，内容与删除前完全一致，未做任何修改）`)
    }
    lines.push(`2. 把 \`sessions\` 里的每个会话目录移动回 \`${join(dshHome(), 'sessions', manifest.recordsDirName || '<原工作区目录>')}\`。`)
    lines.push('3. 打开 DeepSeek Harness → 添加工作区 → 选择上面的项目路径。会话记录放回后会自动与该工作区关联。')
    lines.push('')
    lines.push('## 说明')
    lines.push('')
    lines.push('- 本回收站里的内容只是"搬了个位置"，**没有任何文件被修改或删除**。')
    lines.push('- 确认不再需要时，直接删除本目录即可释放空间。')
    lines.push('- 恢复脚本不会覆盖已存在的文件：若目标已存在，它会停下来提示你。')
    lines.push('')
    writeFileSync(join(entryDir, '恢复说明.md'), lines.join('\n'), 'utf8')
  }

  /** 写入可直接运行的恢复脚本（PowerShell，UTF-8 BOM，含中文提示）。 */
  writeRestoreScript(entryDir, manifest) {
    const projectBlock = manifest.kind === 'workspace' && manifest.projectPath
      ? [
        `$target = '${manifest.projectPath.replace(/'/g, "''")}'`,
        `if (Test-Path -LiteralPath $target) { Write-Host "[跳过] 目标已存在，未覆盖：$target" -ForegroundColor Yellow }`,
        `else {`,
        `  $parentDir = Split-Path -Parent $target`,
        `  if (-not (Test-Path -LiteralPath $parentDir)) { New-Item -ItemType Directory -Force -Path $parentDir | Out-Null }`,
        `  Move-Item -LiteralPath $projectSrc -Destination $target -Force`,
        `  Write-Host "[完成] 项目文件夹已还原到 $target" -ForegroundColor Green`,
        `}`,
      ].join('\n')
      : ''
    const sessionsBlock = (manifest.sessionIds && manifest.sessionIds.length > 0 && manifest.recordsDirName)
      ? [
        `$recordsParent = Join-Path $dshHome 'sessions\\${manifest.recordsDirName.replace(/'/g, "''")}'`,
        `if (-not (Test-Path -LiteralPath $recordsParent)) { New-Item -ItemType Directory -Force -Path $recordsParent | Out-Null }`,
        `Get-ChildItem -LiteralPath $sessionSrc -Directory | ForEach-Object {`,
        `  $dest = Join-Path $recordsParent $_.Name`,
        `  if (Test-Path -LiteralPath $dest) { Write-Host "[跳过] 会话记录已存在：$($_.Name)" -ForegroundColor Yellow }`,
        `  else { Move-Item -LiteralPath $_.FullName -Destination $dest -Force; Write-Host "[完成] 会话记录已还原：$($_.Name)" -ForegroundColor Green }`,
        `}`,
      ].join('\n')
      : ''
    const script = [
      '# DSH Recycle Bin 恢复脚本（由 dsh-cleaner 生成）',
      '# 直接运行即可把项目文件夹与会话记录搬回删除前的位置；不会覆盖已存在的文件。',
      '$ErrorActionPreference = \'Stop\'',
      '$here = Split-Path -Parent $MyInvocation.MyCommand.Path',
      `$dshHome = '${dshHome().replace(/'/g, "''")}'`,
      '$projectSrc = Get-ChildItem -LiteralPath $here -Directory | Where-Object { $_.Name -ne \'sessions\' } | Select-Object -First 1',
      '$sessionSrc = Join-Path $here \'sessions\'',
      projectBlock,
      sessionsBlock,
      'Write-Host \'\'',
      'Write-Host \'完成。请打开 DeepSeek Harness，用「添加工作区」重新登记项目路径。\' -ForegroundColor Cyan',
      'Read-Host \'按回车关闭\'',
    ].filter((line) => line !== '').join('\n')
    writeFileSync(join(entryDir, '恢复.ps1'), '\uFEFF' + script + '\n', 'utf8')
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

  /** 项目路径的硬性安全检查：命中任何一条都拒绝搬运。 */
  assertProjectPathSafe(projectPath) {
    if (!projectPath || projectPath.trim() === '') throw new Error('工作区没有可用的项目路径')
    if (!existsSync(projectPath)) throw new Error(`项目路径不存在：${projectPath}`)
    if (!statSync(projectPath).isDirectory()) throw new Error(`项目路径不是文件夹：${projectPath}`)
    const p = resolve(projectPath)
    if (samePath(p, parse(p).root)) throw new Error(`拒绝搬运驱动器根目录：${p}`)
    if (samePath(p, homedir())) throw new Error(`拒绝搬运用户主目录：${p}`)
    if (samePath(p, dshHome())) throw new Error(`拒绝搬运 DSH 主目录：${p}`)
    if (isAncestor(p, recycleBin())) throw new Error(`项目路径包含回收站，拒绝搬运：${p}`)
    if (isAncestor(recycleBin(), p)) throw new Error(`项目路径位于回收站内，拒绝搬运：${p}`)
    if (isAncestor(p, dshHome())) throw new Error(`项目路径包含 DSH 主目录，拒绝搬运：${p}`)
    if (isAncestor(p, process.cwd())) throw new Error(`项目路径包含当前工作目录，拒绝搬运：${p}`)
    const blocked = [
      join(homedir(), 'AppData'),
      process.env.SystemRoot || 'C:\\Windows',
      process.env.ProgramFiles || 'C:\\Program Files',
      process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)',
      process.env.ProgramData || 'C:\\ProgramData',
      join(homedir(), 'Desktop'),
      join(homedir(), 'Documents'),
      join(homedir(), 'Downloads'),
    ].filter(Boolean)
    for (const dir of blocked) {
      if (samePath(p, dir)) throw new Error(`拒绝搬运系统/用户目录本身：${p}`)
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
      let projectBytes = 0
      try {
        if (path && existsSync(path)) projectBytes = this.dirStats(path).bytes
      } catch { }
      workspaces.push({
        id,
        title,
        path,
        sessions,
        bytes: sessions.reduce((sum, s) => sum + (s.bytes || 0), 0),
        projectBytes,
      })
    }
    // 未登记在册的目录：`session-*` 是"已从列表移除、记录仍保留"的会话记录；
    // 其余（多为 api-* / od-* 残留）算孤儿。
    const seenOrphans = new Set()
    const orphans = []
    const detached = []
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
          const view = this.sessionView(name, proj, archivedSet)
          if (name.startsWith('session-')) detached.push(view)
          else orphans.push(view)
        }
      }
    }
    return { workspaces, orphans, detached }
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

  /** 会话记录目录在原工作区下的父目录名（用于还原时放回原处）。 */
  recordsDirNameOf(sessionId) {
    for (const dir of this.sessionDirs(sessionId)) return basename(dirname(dir))
    return null
  }

  /**
   * 删除会话 = 仅解除 dsh 与该会话记录的关联（从会话列表里消失）。
   * 磁盘上的任何真实文件都不动：会话记录目录原地保留。
   * 需要连记录一起清掉时，面板「已从列表移除（记录仍保留）」里可以显式移入回收站。
   */
  async deleteSession(sessionId) {
    sessionId = String(sessionId)
    if (sessionId === '') throw new Error('缺少 sessionId')
    this.assertNotOpen(sessionId)
    const handle = this.ownerHandleOf(sessionId)
    if (!handle) {
      throw new Error('这个会话不在任何工作区登记里：它已从列表移除（记录仍保留），可在「已从列表移除」一栏把它移入回收站')
    }
    await handle.detachSession(sessionId)   // 产品原生：只摘登记，走 storage 写链并广播变更
    return {
      ok: true,
      detached: true,
      filesUntouched: true,
      moved: [],
      freed: 0,
      note: '仅解除关联：会话记录仍原样保留在磁盘上',
    }
  }

  /**
   * 删除工作区 = 解除与 dsh 的关联 + 项目文件夹（含全部文件，原样）与会话记录
   * 一起搬进 DSH Recycle Bin，并在回收条目内写好恢复引导。
   */
  async deleteWorkspace(workspaceId) {
    workspaceId = String(workspaceId)
    let handle = null
    try { handle = this.ctx.workspaceRegistry.get(workspaceId) } catch { }
    if (!handle) throw new Error(`工作区「${workspaceId}」不存在（可能已被删除）`)
    const sessionIds = [...handle.sessionIds]
    for (const sid of sessionIds) this.assertNotOpen(sid)
    const projectPath = handle.path
    this.assertProjectPathSafe(projectPath)

    const recordsDirName = sessionIds.length > 0 ? (this.recordsDirNameOf(sessionIds[0]) || null) : null
    const title = handle.title || basename(projectPath)
    const { name, entryDir } = this.newRecycleEntry(`workspace_${title}`)

    // 1) 项目文件夹整体搬家（内容不做任何改动）
    const projectName = basename(projectPath)
    const projectDest = join(entryDir, projectName)
    const method = moveDir(projectPath, projectDest)

    // 2) 该工作区的会话记录搬到同一回收条目的 sessions/ 下
    let sessionCount = 0
    const sessionDest = join(entryDir, 'sessions')
    for (const sid of sessionIds) {
      for (const dir of this.sessionDirs(sid)) {
        mkdirSync(sessionDest, { recursive: true })
        moveDir(dir, join(sessionDest, basename(dir)))
        sessionCount += 1
      }
    }

    // 3) 解除与 dsh 的关联（先摘会话登记，再删工作区登记）
    for (const sid of sessionIds) {
      try { await handle.detachSession(sid) } catch { }
    }
    const deleted = await this.ctx.workspaceRegistry.delete(workspaceId)

    // 4) 回收条目元数据与恢复引导
    const manifest = {
      kind: 'workspace',
      workspaceId,
      title,
      projectPath,
      projectName,
      recordsDirName,
      sessionIds,
      dirName: projectName,
      fromDir: dirname(projectPath),
      when: new Date().toISOString(),
    }
    writeFileSync(join(entryDir, 'manifest.json'), JSON.stringify(manifest, null, 2))
    this.writeRestoreGuide(entryDir, manifest)
    this.writeRestoreScript(entryDir, manifest)

    const stats = this.dirStats(entryDir)
    return {
      ok: true,
      deleted: deleted !== false,
      moved: method === 'rename' ? 'move' : 'copy',
      project: projectPath,
      sessions: sessionCount,
      recycleEntry: name,
      recycleBin: recycleBin(),
      freed: stats.bytes,
    }
  }

  /**
   * 按标题解除关联（供会话行 ⋯ 菜单里的「从列表移除」使用）：
   * 菜单在 DOM 里与行没有连接，只有 ⋯ 按钮 aria-label 里的标题可用。
   * 同名会话会有歧义——此时用所在分组的标题（工作区）区分，仍歧义则拒绝并说明。
   */
  async detachByTitle(title, workspaceTitle) {
    const want = String(title || '').trim()
    if (want === '') throw new Error('缺少会话标题')
    const proj = this.readProjections()
    const archivedSet = new Set((this.ctx.workspaceRegistry.archivedSessionIds || []).map(String))
    const hits = []
    for (const w of this.ctx.workspaceRegistry.list()) {
      let handle = null
      try { handle = this.ctx.workspaceRegistry.get(String(w.id)) } catch { continue }
      const views = (handle ? [...handle.sessionIds] : []).map((sid) => this.sessionView(String(sid), proj, archivedSet))
      for (const v of views) {
        const t = (v.title || '').trim()
        if (t === want || v.id === want) hits.push({ handle, view: v, workspace: String(handle.title || w.title || '') })
      }
    }
    if (hits.length === 0) throw new Error(`列表里找不到标题为「${want}」的会话（可能已被移除）`)
    let target = hits[0]
    if (hits.length > 1) {
      const hint = String(workspaceTitle || '').trim()
      const narrowed = hint === '' ? [] : hits.filter((h) => h.workspace.trim() === hint)
      if (narrowed.length === 1) target = narrowed[0]
      else throw new Error(`有 ${hits.length} 个同名会话「${want}」，无法确定是哪一个：请在「清理」面板里操作（那里按工作区分组）`)
    }
    this.assertNotOpen(target.view.id)
    await target.handle.detachSession(target.view.id)
    return {
      ok: true,
      detached: true,
      filesUntouched: true,
      sessionId: target.view.id,
      title: want,
      workspace: target.workspace,
      note: '仅解除关联：会话记录仍原样保留在磁盘上',
    }
  }

  /** 把一条"已从列表移除"的记录重新登记回工作区（产品会校验 cwd，只有对的那个工作区能成功）。 */
  async attachSession(sessionId) {
    sessionId = String(sessionId)
    if (sessionId === '') throw new Error('缺少 sessionId')
    if (this.sessionDirs(sessionId).length === 0) {
      throw new Error(`磁盘上找不到会话「${sessionId}」的记录，无法重新加入列表`)
    }
    const errors = []
    for (const w of this.ctx.workspaceRegistry.list()) {
      let handle = null
      try { handle = this.ctx.workspaceRegistry.get(String(w.id)) } catch { continue }
      if (!handle || typeof handle.attachSession !== 'function') continue
      try {
        await handle.attachSession(sessionId)
        return { ok: true, sessionId, workspaceId: String(handle.id), workspace: String(handle.title || '') }
      } catch (error) {
        errors.push(`${handle.title || handle.id}: ${error instanceof Error ? error.message : String(error)}`)
      }
    }
    throw new Error(`没有工作区能重新接纳这个会话（记录里的 cwd 与登记的工作区路径都对不上）：${errors.slice(0, 3).join(' / ')}`)
  }

  /** 按标题删工作区（供工作区行 ⋯ 菜单里被接管的「删除工作区」使用）。 */
  async deleteWorkspaceByTitle(title) {
    const want = String(title || '').trim()
    if (want === '') throw new Error('缺少工作区标题')
    const hits = []
    for (const w of this.ctx.workspaceRegistry.list()) {
      const id = String(w.id)
      let handle = null
      try { handle = this.ctx.workspaceRegistry.get(id) } catch { }
      const t = String((handle && handle.title) || w.title || '').trim()
      if (t === want || id === want) hits.push(id)
    }
    if (hits.length === 0) throw new Error(`找不到标题为「${want}」的工作区（可能已被删除）`)
    if (hits.length > 1) throw new Error(`有 ${hits.length} 个同名工作区「${want}」，无法确定是哪一个`)
    return await this.deleteWorkspace(hits[0])
  }

  async deleteOrphan(sessionId) {
    sessionId = String(sessionId)
    this.assertNotOpen(sessionId)
    const dirs = this.sessionDirs(sessionId)
    if (dirs.length === 0) throw new Error(`磁盘上找不到会话「${sessionId}」的目录`)
    const recordsDirName = this.recordsDirNameOf(sessionId)
    const moved = []
    for (const dir of dirs) {
      const { name, entryDir } = this.newRecycleEntry(`orphan_${sessionId}`)
      moveDir(dir, join(entryDir, basename(dir)))
      const manifest = {
        kind: 'orphan',
        sessionId,
        workspaceId: null,
        recordsDirName,
        dirName: basename(dir),
        fromDir: dirname(dir),
        when: new Date().toISOString(),
      }
      writeFileSync(join(entryDir, 'manifest.json'), JSON.stringify(manifest, null, 2))
      this.writeRestoreGuide(entryDir, manifest)
      this.writeRestoreScript(entryDir, { ...manifest, sessionIds: [sessionId] })
      moved.push({ name, bytes: this.dirStats(entryDir).bytes })
    }
    return { ok: true, moved, freed: moved.reduce((sum, m) => sum + (m.bytes || 0), 0) }
  }

  recycleList() {
    const bin = recycleBin()
    const entries = []
    if (!existsSync(bin)) return { ok: true, bin, entries }
    for (const name of readdirSync(bin, { withFileTypes: true })) {
      if (!name.isDirectory()) continue
      const entryDir = join(bin, name.name)
      let manifest = {}
      try { manifest = JSON.parse(readFileSync(join(entryDir, 'manifest.json'), 'utf8')) } catch { }
      const stats = this.dirStats(entryDir)
      entries.push({
        name: name.name,
        kind: manifest.kind || null,
        title: manifest.title || null,
        projectPath: manifest.projectPath || null,
        sessionId: manifest.sessionId || manifest.dirName || name.name,
        workspaceId: manifest.workspaceId || null,
        restorable: existsSync(join(entryDir, 'manifest.json')),
        when: manifest.when || null,
        bytes: stats.bytes,
      })
    }
    entries.sort((a, b) => String(b.when || '').localeCompare(String(a.when || '')))
    return { ok: true, bin, entries }
  }

  /** 恢复一个回收条目（工作区条目：项目文件夹 + 会话记录；会话条目：记录目录）。 */
  async restore(name) {
    name = String(name)
    const bin = recycleBin()
    const entryDir = join(bin, name)
    const manifestPath = join(entryDir, 'manifest.json')
    if (!existsSync(manifestPath)) throw new Error(`回收条目「${name}」不存在或没有恢复清单`)
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))

    if (manifest.kind === 'workspace') {
      if (!manifest.projectPath || !manifest.projectName) throw new Error('回收条目的清单缺少项目路径')
      const src = join(entryDir, manifest.projectName)
      if (!existsSync(src)) throw new Error(`回收条目「${name}」里的项目文件夹已缺失`)
      if (existsSync(manifest.projectPath)) throw new Error(`原位置已存在同名文件夹，拒绝覆盖：${manifest.projectPath}`)
      mkdirSync(dirname(manifest.projectPath), { recursive: true })
      moveDir(src, manifest.projectPath)

      let restored = 0
      const sessionSrc = join(entryDir, 'sessions')
      if (existsSync(sessionSrc) && manifest.recordsDirName) {
        const parent = join(this.sessionsRoot(), manifest.recordsDirName)
        mkdirSync(parent, { recursive: true })
        for (const entry of readdirSync(sessionSrc, { withFileTypes: true })) {
          const dest = join(parent, entry.name)
          if (existsSync(dest)) continue
          moveDir(join(sessionSrc, entry.name), dest)
          restored += 1
        }
      }
      let registered = false
      try {
        await this.ctx.workspaceRegistry.create(manifest.projectPath)
        registered = true
      } catch { }
      try { rmSync(entryDir, { recursive: true, force: true }) } catch { }
      return { ok: true, project: manifest.projectPath, sessions: restored, registered }
    }

    if (!manifest.dirName || !manifest.fromDir) throw new Error(`回收条目「${name}」的清单缺少原始位置`)
    const inner = join(entryDir, manifest.dirName)
    if (!existsSync(inner)) throw new Error(`回收条目「${name}」的数据目录已缺失`)
    const targetParent = existsSync(manifest.fromDir) ? manifest.fromDir : join(this.sessionsRoot(), manifest.recordsDirName || '')
    if (!targetParent) throw new Error('无法确定会话记录的原位置')
    mkdirSync(targetParent, { recursive: true })
    const target = join(targetParent, manifest.dirName)
    if (existsSync(target)) throw new Error(`目标位置已存在同名会话目录，无法恢复：${manifest.dirName}`)
    moveDir(inner, target)
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

  /**
   * 自检：A) 登记级 create → list → delete → gone；
   * B) 用临时项目跑一遍完整搬家循环（项目 → DSH Recycle Bin → 恢复），
   *    校验项目文件字节不变、恢复引导就位、恢复后回到原位。全程只碰 %TEMP%。
   */
  async selftest() {
    const result = {}

    // A) 登记级
    const dir = join(tmpdir(), 'dsh-cleaner-selftest-' + Date.now())
    mkdirSync(dir, { recursive: true })
    const handle = await this.ctx.workspaceRegistry.create(dir)
    const id = String(handle.id)
    result.created = this.ctx.workspaceRegistry.list().some((w) => String(w.id) === id)
    result.deleted = (await this.ctx.workspaceRegistry.delete(id)) !== false
    result.gone = !this.ctx.workspaceRegistry.list().some((w) => String(w.id) === id)

    // B) 完整搬家循环
    const projectDir = join(tmpdir(), 'dsh-cleaner-cycle-' + Date.now())
    mkdirSync(join(projectDir, 'sub'), { recursive: true })
    writeFileSync(join(projectDir, 'sub', 'probe.txt'), 'CYCLE-PROBE')
    const h2 = await this.ctx.workspaceRegistry.create(projectDir)
    const del = await this.deleteWorkspace(String(h2.id))
    result.projectMovedAway = !existsSync(projectDir)
    const entryDir = join(recycleBin(), String(del.recycleEntry || ''))
    const probeInBin = join(entryDir, basename(projectDir), 'sub', 'probe.txt')
    result.projectInsideBin = existsSync(probeInBin)
    result.probeIntact = existsSync(probeInBin) && readFileSync(probeInBin, 'utf8') === 'CYCLE-PROBE'
    result.guideWritten = existsSync(join(entryDir, '恢复说明.md')) && existsSync(join(entryDir, '恢复.ps1'))
    const back = await this.restore(String(del.recycleEntry || ''))
    const probeBack = join(projectDir, 'sub', 'probe.txt')
    result.restored = back.ok === true && existsSync(probeBack) && readFileSync(probeBack, 'utf8') === 'CYCLE-PROBE'
    result.recycleBin = recycleBin()

    // 清理自检痕迹（登记 + 临时目录）
    try {
      for (const w of this.ctx.workspaceRegistry.list()) {
        if (samePath(w.path, projectDir) || samePath(w.path, dir)) await this.ctx.workspaceRegistry.delete(String(w.id))
      }
    } catch { }
    try { rmSync(projectDir, { recursive: true, force: true }) } catch { }
    try { rmSync(dir, { recursive: true, force: true }) } catch { }

    result.ok = Object.entries(result).every(([k, v]) => k === 'recycleBin' || v !== false)
    return result
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
        return { ok: true, recycleBin: recycleBin(), ...this.listWorkspaces() }
      case 'delete-session':
        return await this.deleteSession(args.sessionId)
      case 'detach-title':
        return await this.detachByTitle(args.title, args.workspaceTitle)
      case 'attach-session':
        return await this.attachSession(args.sessionId)
      case 'delete-workspace':
        return await this.deleteWorkspace(args.workspaceId)
      case 'delete-workspace-by-title':
        return await this.deleteWorkspaceByTitle(args.title)
      case 'delete-orphan':
        return await this.deleteOrphan(args.sessionId)
      case 'recycle-list':
        return this.recycleList()
      case 'restore':
        return await this.restore(args.name)
      case 'selftest':
        return await this.selftest()
      // 兼容 v1 客户端的方法名
      case 'trash-list':
        return this.recycleList()
      default:
        return { ok: false, reason: `unknown-method:${method}` }
    }
  }
}

export default CleanerService
