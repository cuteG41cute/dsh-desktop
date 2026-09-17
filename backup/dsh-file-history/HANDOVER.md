# 交接：dsh-file-history（改前自动备份）

> 给"以后接手这个项目的 agent/人"的最小必要上下文。功能细节见同目录 `README.md` 与
> `~/.dsh/skills/dsh-file-history/SKILL.md`；这里只放**部署事实、验证入口、和必须遵守的约定**。

## 1. 现在跑着什么（部署事实）

| 项目 | 值 |
| --- | --- |
| 插件 | `dsh-file-history`（版本见 `package.json`） |
| 已安装位置 | `~/.dsh/profiles/web/node_modules/dsh-file-history/`（宿主 `lib/index.js` + 客户端 `lib/client.js`） |
| 加载登记 | `~/.dsh/profiles/web/cordis.patch.yml` 里的 `- id: dsh-file-history`（`inject: [tools, settings, timer, agents]`） |
| 配置 | `~/.dsh/settings.yaml` → `file-history` 段（**热生效**，不用重启） |
| 备份落点 | 项目内 `<项目根>/.dsh-backup/`；项目外文件落 `~/.dsh/file-history/` 兜底 |
| 开关粒度 | **项目级**：`projects[<项目目录>]` 覆盖 > `enabled`（全局默认） |
| 客户端 UI | 会话右上角「备份」状态芯片 + 面板；同一开关也在「设置 → 通用」 |
| RPC | `POST /dsh-file-history/api`（`state` / `set-enabled` / `reset-project`） |

改了源码之后**必须重跑安装脚本 + 重启 dsh 服务**：宿主侧 `@deepseek-ai/cordis-plugin-hmr` 在
`dsh-base` 里是 `disabled: true`，`cordis.patch.yml` 不会热加载新插件（客户端半边还需要刷新页面）。

## 2. 三个入口验证（按"从轻到重"）

```powershell
# ① 面板：右上角芯片的灯色 + 面板里的实时流水（最省事，平时用这个）
# ② 命令行一次看清 / 实时盯梢 / 扫全机
powershell -ExecutionPolicy Bypass -File monitor.ps1 -Project "<项目目录>"
powershell -ExecutionPolicy Bypass -File monitor.ps1 -Watch -Project "<项目目录>"
powershell -ExecutionPolicy Bypass -File monitor.ps1 -Scan
# ③ 回归测试（改代码后必跑）
node selftest.mjs                                   # 仓库内，假 ctx，59 项断言
node "$env:USERPROFILE\.dsh\profiles\web\node_modules\dsh-file-history\host-contract-check.mjs"   # 真依赖，9 项断言
```

**健康判据**：`<项目>/.dsh-backup/_dsh-file-history/status.json` 的 `at` 在刷新、`lastError` 为 null；
`manifest.jsonl` 的尾部有对应记录。两者都是**只读、可随时删**的观测产物。

## 3. 必须遵守的宿主接口约定（踩过坑）

1. **`ctx.settings.register(ns, schema, opts)` 的 `schema` 必须是 schemastery Schema**，
   不能是工厂函数 `(s) => s.object({...})`。宿主 `dsh-settings` 的 `resolve()` 是
   `schema(mergeLayers(base, section))` —— 它把合并后的**普通配置对象当参数调用** schema，
   工厂写法会让 `s` 变成那个对象，报 `s.boolean is not a function`，**插件一加载就炸**。
   正确：`import s from '@deepseek-ai/schemastery'` + `s.object({...})`。
2. **用 `ctx.timeout`/`ctx.setTimeout` 就必须 `inject` 里带 `timer`**（timer 服务靠 `ctx.mixin` 混入），
   否则报 `cannot get property "timer" without inject`；`ctx.setTimeout` 已 deprecated，统一用 `ctx.timeout`。
3. **删设置项必须走 `ctx.settings.mutate(op:'unset')`**：`update()` 是合并语义，删不掉键
   （「改为跟随全局默认」就是靠这条实现的）。
4. **提交前别用"看起来很合理"的假设**：离线自测用替身，**证明不了真依赖的契约** ——
   真依赖语义由 `host-contract-check.mjs` 在 profile 内保证。这两条 bug 就是这么漏出去的。

## 4. 本机环境注意事项

- **`.ps1` 必须带 UTF-8 BOM**：Windows PowerShell 5.1（本机没有 `pwsh`）对无 BOM 脚本按 ANSI(GBK) 解码，
  中文注释会把语法搞坏（`Unexpected token`）。补 BOM：
  `[System.IO.File]::WriteAllText($f, [System.IO.File]::ReadAllText($f,[Text.Encoding]::UTF8), [Text.UTF8Encoding]::new($true))`
- **`Start-Process` 传带空格路径会被参数拆分**：`monitor.ps1` 支持用环境变量 `FH_PROJECT` 传项目目录。
- **别用 `FileHandle.read(buf, off, len, position)` 读日志**：在本机 Windows 上静默失败；
  用 `readFile()` + 尾部切片。**别写空 catch**：这个 bug 曾被 `catch { return [] }` 藏了半天。
- 项目外文件的备份命中"最后一个用户目录"时，`~/.dsh/file-history` 会持续增长，靠 `maxAgeDays`/`maxProjectBytes` 收敛。

## 5. 现在可以放心依赖的行为

- 任何 `write`/`edit` **覆盖已存在文件**前自动备份；新建文件不备份；二进制/超大文件只记指纹（`restorable=false`）。
- 备份失败 → **拦下这次写入**（fail-closed），原因写进 `status.json.lastError` 并回给模型。
- 每个源文件默认保留最近 5 代；项目被单独关掉时，系统提示里的备份说明也**不会**再注入。
- `file_history` 工具：`list` / `show`（与当前文件 diff）/ `restore` / `revert_turn`（整轮回退）。
- `.dsh-backup/` 自身不会被再备份；有 git 时会向上找到仓库根登记 `.gitignore`（嵌套工作区也正确）。
