# dsh-file-history

DeepSeek Harness 的「**改前自动备份**」插件：让 agent 改文件这件事从"靠自觉备份"变成"harness 兜底"。

- 任何 `write` / `edit` **覆盖已存在文件**之前，自动把原文逐字节备份进**项目内**的 `.dsh-backup/`；
- 备份文件名 = **源文件名 + 时间戳 + 原扩展名**，按源文件路径镜像存放；
- **每个源文件只保留最近 5 轮**（`maxGenerations`，可就地调整），另加天数与容量两层兜底；
- 备份失败就**拦下这次写入**（fail-closed），不会出现"没备份却照样改坏"；
- 模型侧有 `file_history` 工具（`list` / `show` / `restore` / `revert_turn`），系统提示里也常驻几行说明，
  **agent 知道备份系统的存在、位置与恢复方式**；
- 运行状况标志：`.dsh-backup/_dsh-file-history/status.json`（时间戳每次备份/还原刷新）。

## 为什么需要它

harness 原生只有 `dsh-atomic-write`（写入原子）和 `dsh-fs-observation-policy`（先读后写）——
**原子不等于可撤销**。文件被覆盖或删掉之后，唯一的补救是让模型重读上下文再写一遍：
既烧 token，又可能二次改错。本插件把原文留在工具层，回滚变成一次工具调用（或一次文件复制）。

## 备份长什么样

```
<项目根>/.dsh-backup/
├── src/lib/nested.20260917-095500.ts      # 子目录按源路径镜像
├── src/lib/nested.20260917-095500.ts.json # 该备份的元数据
├── demo.20260917-095500.txt
├── demo.20260917-095500.txt.json
└── _dsh-file-history/
    ├── status.json                        # ★ 运行状况标志
    └── manifest.jsonl                     # 快照/还原/回退审计流水

~/.dsh/file-history/<工作区>/<文件签名>/<时间戳>/content   # 仅“项目外文件”的兜底目录
```

恢复方式三选一：`file_history(action="restore", path=...)`、`file_history(action="revert_turn")`（整轮），
或直接把人能看懂的备份文件复制回原位。

## 目录

| 文件 | 作用 |
| --- | --- |
| `lib/index.js` | 插件本体：`tools/pre-execute` 备份 + `file_history` 工具 + 系统提示公告 + 保留策略 |
| `package.json` | 插件清单（`type: module`，依赖 `@deepseek-ai/cordis`、`@deepseek-ai/schemastery`） |
| `install.ps1` | 安装/卸载到指定 dsh profile（写 `node_modules` + 登记 `cordis.patch.yml`，自动备份原文件） |
| `selftest.mjs` | 离线自测：假 ctx 直接驱动插件，36 项断言（无需启动 harness） |
| `after-restart-check.ps1` | 重启后体检：插件是否已加载、备份目录是否已创建 |
| `verify.ps1` | 端到端验证：起一个独立 headless dsh，让真实 agent 改坏再还原 |
| `e2e/patch.yml` | 端到端验证用的临时 patch |

## 安装

```powershell
cd "<workspace>\dsh-file-history"
powershell -ExecutionPolicy Bypass -File install.ps1 -Profile web -Force
# 然后重启 dsh 服务 / 桌面版窗口
```

重启是必须的：宿主侧 `@deepseek-ai/cordis-plugin-hmr` 在 `dsh-base` 里 `disabled: true`，
改 `cordis.patch.yml` **不会**热加载新插件（客户端插件 HMR 是另一回事）。

卸载：`powershell -ExecutionPolicy Bypass -File install.ps1 -Remove`（已产生的备份不会被删除）。

## 自测与验证

```powershell
# 离线，秒级，36 项断言
node selftest.mjs
# 重启后的体检
powershell -ExecutionPolicy Bypass -File after-restart-check.ps1
# 端到端，起独立实例，不动正在运行的 3080 服务
powershell -ExecutionPolicy Bypass -File verify.ps1
```

注意：本机 PowerShell 7（`pwsh`）不在 PATH 上，脚本一律用系统自带的
`powershell.exe`（Windows PowerShell 5.1）执行。

## 配置（`~/.dsh/settings.yaml` → `file-history` 段，改动热生效）

```yaml
file-history:
  enabled: true                  # 总开关
  maxFileBytes: 2097152          # 超过只记指纹（默认 2MB）
  maxGenerations: 5              # 每个源文件保留最近几代（默认 5 轮）
  maxAgeDays: 30                 # 备份保留天数
  maxProjectBytes: 536870912     # 单个项目备份区容量上限（默认 512MB）
  announceInPrompt: true         # 把备份系统写进系统提示
  gitignoreBackups: true         # 自动把 .dsh-backup/ 加进项目 .gitignore
```

## 关键实现决策

1. **不改写工具参数**：`tools/pre-execute` 无法改写 `exec.arguments`，所以不做"挡下写入再由插件代写"——
   那会丢掉 harness 原生的 read-before-write 校验与展示层 diff 卡片。这里只做旁路备份 + 校验，原工具照常执行。
2. **fail-closed**：备份读失败/并发修改 → `deny` 本次写入，并把原因回给模型。
3. **同轮分组用 `rootCallId`**：一次助手消息里的多次 `write/edit` 共享 `rootCallId`，`revert_turn` 按它成组回退；
   同一文件多代时回退到**本轮最早那代**（即本轮开始时的样子）。
4. **备份逐字节保存**：不做行尾/编码转换，`restore` 是原样写回。
5. **代数上限就地执行**：每次备份后立刻把该源文件收敛到最近 N 代（不是只靠小时级 sweep），短时间连改也不会堆积。
6. **自身免疫 + git 卫生**：`.dsh-backup/` 内的文件不再被备份；项目有 `.git` 时自动写入 `.gitignore` 一行。
7. **项目外文件不污染无关目录**：落到用户主目录的兜底区，由同一个 `file_history` 工具统一索引。

## 技能与排查

同机已安装配套技能：`~/.dsh/skills/dsh-file-history/SKILL.md`（含完整行为规则、排障表、`file_history` 用法）。
