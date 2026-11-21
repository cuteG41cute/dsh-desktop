// dsh-fence — 用户级实例的工作区围栏（manager 自带插件）
//
// 服务端强制：
//  1. 包装 workspaceRegistry.create(path, title)：任何调用方传入的路径都会被
//     重映射到 <DSH_FENCE_ROOT>/<名称>，目录自动创建；符号链接逃逸被拒绝。
//  2. 暴露 POST /dsh-fence/create { name }：管理器"只填名称"的入口，
//     直接在围栏内建目录并注册工作区，不经过系统文件夹选择器。

import { mkdirSync, realpathSync } from 'node:fs'
import { basename, join, resolve, sep } from 'node:path'

const FENCE_ENV = 'DSH_FENCE_ROOT'
const MARK = Symbol.for('dsh-fence.patched')
const ROUTE = '/dsh-fence/create'

function sanitize(name) {
  let n = String(name || '').trim()
  n = n.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_').replace(/\.+$/g, '')
  if (!n || n === '.' || n === '..') return ''
  return n.slice(0, 80)
}

function within(root, target) {
  const r = resolve(root)
  const t = resolve(target)
  return t === r || t.startsWith(r + sep)
}

export default {
  name: 'dsh-fence',
  inject: ['workspaceRegistry', 'webServer'],

  apply(ctx) {
    const fence = process.env[FENCE_ENV]
    if (!fence) return
    const reg = ctx.workspaceRegistry
    if (!reg) return

    const root = resolve(fence)
    try { mkdirSync(root, { recursive: true }) } catch { return }

    const createInFence = async (rawName, title) => {
      const name = sanitize(rawName)
      if (!name) throw new Error('工作区名称不能为空')
      const target = join(root, name)
      mkdirSync(target, { recursive: true })
      let real = target
      try { real = realpathSync(target) } catch { }
      if (!within(root, real)) throw new Error('工作区路径越过实例围栏')
      return { workspace: await reg.create(real, title || name), name }
    }

    if (!reg[MARK]) {
      const original = reg.create.bind(reg)
      reg.create = async function createInFenceHook(inputPath, title) {
        let name = ''
        try { name = basename(String(inputPath ?? '')) } catch { name = '' }
        const mapped = sanitize(name) || sanitize(title) || 'workspace'
        const target = join(root, mapped)
        mkdirSync(target, { recursive: true })
        let real = target
        try { real = realpathSync(target) } catch { }
        if (!within(root, real)) throw new Error('fence: workspace path escapes the instance directory: ' + real)
        return original(real, title || mapped)
      }
      reg[MARK] = true
    }

    // HTTP 入口：管理器新建工作区只提交名称
    ctx.effect(() => ctx.webServer.register({
      kind: 'exact',
      path: ROUTE,
      handler: async (req, res) => {
        try {
          if (req.method !== 'POST') {
            res.writeHead(405, { 'content-type': 'application/json' })
            res.end(JSON.stringify({ ok: false, error: 'method not allowed' }))
            return
          }
          let body = ''
          for await (const chunk of req) body += chunk
          let payload = {}
          try { payload = JSON.parse(body || '{}') } catch { }
          const { workspace, name } = await createInFence(payload.name, payload.title)
          res.writeHead(200, { 'content-type': 'application/json' })
          res.end(JSON.stringify({
            ok: true,
            name,
            path: workspace?.path ?? join(root, name),
            id: workspace?.id ?? '',
            title: workspace?.title ?? name,
          }))
        } catch (e) {
          res.writeHead(400, { 'content-type': 'application/json' })
          res.end(JSON.stringify({ ok: false, error: String(e?.message || e) }))
        }
      },
    }))

    try { console.log('[dsh-fence] fence root = ' + root) } catch { }
  },
}
