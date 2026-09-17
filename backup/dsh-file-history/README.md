# dsh-file-history

DeepSeek Harness 的「**改前自动快照**」插件：让 agent 改文件这件事从"靠自觉备份"变成"harness 兜底"。

- 任何 `write` / `edit` **覆盖已存在文件**之前，自动把原文逐字节快照到 `~/.dsh/file-history/`；
- 快照失败就**拦下这次写入**（fail-closed），不会出现"没备份却照样改坏"；
- 模型侧只多一个 `file_history` 工具：`list` / `show` / `restore` / `revert_turn`，平时零 token 成本；
- 新建文件不快照、二进制/超大文件只记指纹、有代数/天数/容量三层保留策略。

## 为什么需要它

harness 原生只有 `dsh-atomic-write`（写入原子）和 `dsh-fs-observation-policy`（先读后写）——
**原子不等于可撤销**。文件被覆盖或删掉之后，唯一的补救是让模型重读上下文再写一遍：
既烧 token，又可能二次改错。本插件把原文留在工具层，回滚变成一次工具调用。

## 目录

| 文件 | 作用 |
| --- | --- |
| `lib/index.js` | 插件本体（唯一运行时文件）：`tools/pre-execute` 快照 + `file_history` 工具 + 保留策略 |
| `package.json` | 插件清单（`type: module`，依赖 `@deepseek-ai/cordis`、`@deepseek-ai/schemastery`） |
| `install.ps1` | 安装/卸载到指定 dsh profile（写 `node_modules` + 登记 `cordis.patch.yml`，自动备份原文件） |
| `selftest.mjs` | 离线自测：假 ctx 直接驱动插件，17 项断言（无需启动 harness） |
| `verify.ps1` | 端到端验证：起一个独立 headless dsh，让真实 agent 改坏再还原 |
| `after-restart-check.ps1` | 重启后的体检：插件是否已加载、快照目录是否已创建 |
| `e2e/patch.yml` | 端到端验证用的临时 patch（把插件插进 rescue profile） |

## 安装

```powershell
cd "<workspace>\dsh-file-history"
powershell -ExecutionPolicy Bypass -File install.ps1 -Profile web -Force
# 然后重启 dsh 服务 / 桌面版窗口
```

重启是必须的：宿主侧 `@deepseek-ai/cordis-plugin-hmr` 在 `dsh-base` 里 `disabled: true`，
改 `cordis.patch.yml` **不会**热加载新插件（客户端插件 HMR 是另一回事）。

卸载：`powershell -ExecutionPolicy Bypass -File install.ps1 -Remove`（已产生的历史快照不会被删除）。

## 自测与验证

```powershell
# 离线，秒级，17 项断言
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
  maxAgeDays: 30                 # 保留天数
  maxWorkspaceBytes: 536870912   # 单工作区容量上限（默认 512MB）
  maxEntriesPerFile: 50          # 单文件代数上限
```

## 快照布局

```
~/.dsh/file-history/
├── _sessions/<sessionId>.jsonl          # 快照/还原审计日志
└── <工作区名>-<路径哈希>/<文件名>-<路径哈希>/0001/{meta.json, content}
```

`meta.json` 记录 `originalPath`（还原依据）、`displayPath`、`time`、`size`、`hash`/`hashKind`、
`tool`、`sessionId`、`sessionTurnId`、`stored`、`reason`。

## 关键实现决策

1. **不改写工具参数**：`tools/pre-execute` 无法改写 `exec.arguments`，所以不去做"挡下写入再由插件代写"——
   那会丢掉 harness 原生的 read-before-write 校验与展示层 diff 卡片。这里只做旁路快照 + 校验，原工具照常执行。
2. **fail-closed**：快照读失败/并发修改 → `deny` 本次写入，并把原因回给模型。
3. **同轮分组用 `rootCallId`**：一次助手消息里的多次 `write/edit` 共享 `rootCallId`，`revert_turn` 按它成组回退；
   同一文件多代时回退到**本轮最早那代**（即本轮开始时的样子）。
4. **快照逐字节保存**：不做行尾/编码转换，`restore` 是原样写回。
5. **保留策略就地执行**：代数裁剪发生在每次快照时（不是只靠小时级 sweep），短时间连改也不会堆积。

## 技能与排查

同机已安装配套技能：`~/.dsh/skills/dsh-file-history/SKILL.md`（含完整行为规则、排障表、`file_history` 用法）。
