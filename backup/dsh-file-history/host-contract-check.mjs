// dsh-file-history 宿主契约检查（真依赖版）
//
// 为什么需要它：仓库内的 selftest.mjs 用假 ctx 驱动插件，schema 由替身解析，
// 真依赖（schemastery / timer）的契约它证明不了。这个脚本直接加载真实依赖，
// 复刻 dsh-settings 的调用约定与 timer 服务的混入方式，专治这类「接口不匹配」回归。
//
// 两种运行位置都支持：
//   1) 仓库内（先 npm install）：node host-contract-check.mjs
//   2) profile 内（已安装副本）：node "$HOME/.dsh/profiles/web/node_modules/dsh-file-history/host-contract-check.mjs"
// 找不到 @deepseek-ai/schemastery 时会回退到 $DSH_HOME/profiles/node_modules 里那份。
//
// 背景（2026-09-17 两次真实加载失败）：
//   1) schema 写成工厂函数 (s) => s.object({...})：宿主 dsh-settings resolve() 是
//      `schema(mergeLayers(base, section))`，会把合并后的配置对象当参数调用 schema，
//      于是 s 变成普通对象 → "TypeError: s.boolean is not a function"。
//      正确写法：`import s from '@deepseek-ai/schemastery'` + `s.object({...})`。
//   2) 用了 ctx.setTimeout 却没 inject timer：ctx 上的定时器方法由 timer 服务混入，
//      必须 `inject = ['tools','settings','timer']`（推荐用 ctx.timeout，setTimeout 已 deprecated）。

import { readFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

const results = []
const ok = (label, pass, extra = '') => {
  results.push({ label, pass: Boolean(pass) })
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${label}${extra ? ` — ${extra}` : ''}`)
}

/** 先按普通模块解析（npm install 后可用），再回退到 DSH profile 里那份。 */
async function loadSchemastery() {
  const attempts = ['@deepseek-ai/schemastery']
  const dshHome = process.env.DSH_HOME || join(homedir(), '.dsh')
  const profileDirs = ['profiles', join('profiles', 'web')]
  for (const dir of profileDirs) {
    const candidate = join(dshHome, dir, 'node_modules', '@deepseek-ai', 'schemastery', 'lib', 'index.mjs')
    attempts.push(pathToFileURL(candidate).href)
  }
  const failures = []
  for (const specifier of attempts) {
    try {
      const loaded = await import(specifier)
      return loaded.default
    } catch (error) {
      failures.push(`${specifier}: ${error && error.message ? error.message : error}`)
    }
  }
  console.error('[host-contract-check] 找不到 @deepseek-ai/schemastery。')
  console.error('  仓库内跑：npm install')
  console.error('  profile 内跑：确认 ' + join(dshHome, 'profiles', 'node_modules', '@deepseek-ai', 'schemastery') + ' 存在')
  for (const line of failures) console.error('  · ' + line)
  process.exit(2)
}

let schemaCtor
let mod
let source
try {
  schemaCtor = await loadSchemastery()
  ;[mod, source] = await Promise.all([
    import(pathToFileURL(join(HERE, 'lib', 'index.js')).href),
    readFile(join(HERE, 'lib', 'index.js'), 'utf8'),
  ])
} catch (error) {
  console.error('[host-contract-check] 无法加载插件：' + (error && error.message ? error.message : error))
  console.error('目录：' + HERE)
  process.exit(2)
}

// 契约 1：schema 必须是 schemastery Schema（可调用），而不是工厂函数
const schema = mod.fileHistorySettingsSchema
ok('fileHistorySettingsSchema 是 schemastery Schema（可调用）', typeof schema === 'function' && typeof schema.default === 'function', `typeof=${typeof schema}`)
ok('schema 由真实 schemastery 构造', schema instanceof schemaCtor || typeof schemaCtor.object === 'function')

// 契约 2：宿主用 schema(值) 解析 —— 默认值与用户覆盖都要正确
const defaults = schema({})
ok(
  'schema({}) 解析出全部默认值',
  defaults.enabled === true &&
    defaults.maxGenerations === 5 &&
    defaults.maxFileBytes === 2 * 1024 * 1024 &&
    defaults.maxAgeDays === 30 &&
    defaults.maxProjectBytes === 512 * 1024 * 1024 &&
    defaults.announceInPrompt === true &&
    defaults.gitignoreBackups === true,
  JSON.stringify(defaults),
)
const overridden = schema({ maxGenerations: 3, enabled: false, unknownKey: 1 })
ok('用户覆盖生效', overridden.maxGenerations === 3 && overridden.enabled === false, JSON.stringify(overridden))
// schemastery 的 object schema 是宽松的（未知键原样保留），这是它的既定语义：
// 后果只是用户在 settings.yaml 里多写的键会被透传，插件只读自己认识的键，不会因此出错。
ok('未知键按 schemastery 既定语义透传（不影响插件读取）', overridden.unknownKey === 1)
let rejected = false
try {
  schema({ maxGenerations: -1 })
} catch {
  rejected = true
}
ok('非法值被 schema 拒绝（负数代数）', rejected)

// 契约 3：inject 必须覆盖用到的服务（timer 是历史上踩过的坑）
const inject = Array.isArray(mod.inject) ? mod.inject : []
ok('inject 覆盖 tools/settings/timer', ['tools', 'settings', 'timer'].every((name) => inject.includes(name)), JSON.stringify(inject))

// 契约 4：定时器只用 ctx.timeout（ctx.setTimeout 已 deprecated）
ok('源码使用 ctx.timeout（未用 deprecated 的 ctx.setTimeout）', source.includes('ctx.timeout(') && !source.includes('ctx.setTimeout('))

// 契约 5：宿主调用路径不抛异常（模拟 settings.register 的 resolve）
let applyError
try {
  const captured = {}
  const ctx = {
    settings: {
      register: (ns, sch) => {
        captured.ns = ns
        sch({}) // 宿主 resolve 的核心动作
        return { get: () => sch({}), watch: () => () => {} }
      },
    },
    tools: { register: () => {} },
    on: () => {},
    get: () => undefined,
    timeout: () => () => {},
    logger: {},
  }
  mod.apply(ctx, {})
  ok('apply() 在宿主调用约定下不抛异常且注册了命名空间', captured.ns === 'file-history', String(captured.ns))
} catch (error) {
  applyError = error
  ok('apply() 在宿主调用约定下不抛异常且注册了命名空间', false, `${error.constructor.name}: ${error.message}`)
}

const failed = results.filter((entry) => !entry.pass)
console.log(`\n===== ${results.length - failed.length}/${results.length} passed =====`)
if (failed.length) {
  console.log('FAILED: ' + failed.map((entry) => entry.label).join('; '))
  process.exit(1)
}
