// dsh-fence — 用户级实例的工作区围栏（manager 自带插件）
//
// 服务端强制：无论调用方是 DSH Web UI、浏览器直连还是 dsh-api，
// 所有 workspaceRegistry.create(path, title) 都会落到 <DSH_FENCE_ROOT>/<名称>。
// 名称取传入路径的最后一段（或 title），非法字符会被替换。
//
// 配合管理器在启动用户级实例时设置 DSH_FENCE_ROOT 与 workspace-write 权限；
// 操作系统级围栏（bwrap / AppContainer）负责读写边界，本插件负责"工作区只能
// 建在实例目录内"这一条策略。

import { mkdirSync, realpathSync } from 'node:fs'
import { basename, dirname, join, resolve, sep } from 'node:path'

const FENCE_ENV = 'DSH_FENCE_ROOT'
const MARK = Symbol.for('dsh-fence.patched')

function sanitize(name) {
  let n = String(name || '').trim()
  n = n.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_').replace(/\.+$/g, '')
  if (!n || n === '.' || n === '..') n = 'workspace'
  return n.slice(0, 80)
}

function within(root, target) {
  const r = resolve(root)
  const t = resolve(target)
  return t === r || t.startsWith(r + sep)
}

export default {
  name: 'dsh-fence',
  inject: ['workspaceRegistry'],

  apply(ctx) {
    const fence = process.env[FENCE_ENV]
    if (!fence) return
    const reg = ctx.workspaceRegistry
    if (!reg || reg[MARK]) return

    const root = resolve(fence)
    try { mkdirSync(root, { recursive: true }) } catch { return }

    const original = reg.create.bind(reg)

    reg.create = async function createInFence(inputPath, title) {
      const raw = String(inputPath ?? '')
      let name = ''
      try { name = basename(raw) } catch { name = '' }
      name = sanitize(name || title)
      let target = join(root, name)

      try { mkdirSync(target, { recursive: true }) } catch (e) {
        throw new Error(`fence: cannot create workspace directory '${target}': ${e.message}`)
      }

      // 防符号链接逃逸：真实路径必须仍在围栏内
      let real = target
      try { real = realpathSync(target) } catch { }
      if (!within(root, real)) {
        throw new Error(`fence: workspace path escapes the instance directory: ${real}`)
      }

      // 若同名目录已被映射过，仍调用原始 create（会返回已有工作区）
      // 若此时父级被替换成链接，真实路径校验会拦住。
      return original(real, title || name)
    }
    reg[MARK] = true
    try { console.log('[dsh-fence] fence root = ' + root) } catch { }
  },
}
