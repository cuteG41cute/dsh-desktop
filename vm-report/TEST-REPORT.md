# dsh-manager Windows · 虚拟机端到端实测报告

测试环境：Hyper-V「Windows 11 开发环境」`WINDEV2407EVAL`（Windows 11 Enterprise Evaluation，Build 22621.3880）
接入方式：`ssh User@172.30.26.56`（OpenSSH 公钥）+ 会话内**常驻代理**（读 `req.txt` 执行动作、写 `res.txt`、随时截屏）
被测版本：2.0.17 → 2.0.23（按实测缺陷逐版修复）
证据目录：`vm-report/*.png`、VM 内 `web.log` / `ui.log` / 实例日志

---

## 一、通过项

### 安装与首启

| 项目 | 证据 | 结果 |
| --- | --- | --- |
| 干净系统安装 | `install-win.ps1` | ✅ 装到 `%LOCALAPPDATA%\Programs\DSH Manager` |
| 首次启动 | `t01_main219.png` | ✅ 窗口正常，进程在交互会话（session 2） |
| 空状态 | 同上 | ✅「未发现 DSH 安装 / ● 未安装」，扫描位置列全（npx 缓存 / %APPDATA%\npm / %DSH_HOME%\profiles / PATH） |
| 四角圆角 | `s01_state.png`、`t01_main219.png` | ✅ 移动、改尺寸后仍是圆角，壁纸从圆角外透出 |
| 托盘 / 单实例 | 实测 | ✅ 关窗后进程仍在托盘；再次启动 exe 能把窗口叫回来 |

### 新建实例

| 项目 | 证据 | 结果 |
| --- | --- | --- |
| 对话框 | `t02_dialog.png` | ✅ 五字段可编辑；日志卡片默认不显示（BUG-3 已修） |
| 默认目录 | VM 干净环境 | ✅ 自动生成 `instances\dsh-new` |
| 目录校验 | `d03_guard.png` | ✅ 指向已有非空目录 → 「目录已存在且不为空，请换一个目录」，不开始安装 |
| **源码安装全流程** | `t04_started.png` → `t08_done.png` | ✅ `git clone` → 实例内 pnpm → `pnpm install` → `pnpm run build` → 生成空 `dsh-home`；VM 内约 22 分钟 |
| 实例卡片 | `t08_done.png` | ✅ 标题=目录名 `dsh-new`、dsh `0.2.2-rc.1`、Node `27.0.0-alpha.0`、端口 3081 |

### 实例生命周期

| 项目 | 证据 | 结果 |
| --- | --- | --- |
| 启动服务 | `t10_running.png` | ✅ 状态「运行中」、PID 7484、端口 3081，按钮变「停止」，快捷控制「服务正常」 |
| 服务真实监听 | `logs\<id>.log`、`Get-NetTCPConnection` | ✅ `dsh web: http://127.0.0.1:3081/?token=…`，3081 有监听 |
| 停止服务 | `s02_stopped.png` | ✅ 状态回「未运行」、PID `—`、node 消失、端口释放、按钮回「启动」，提示「服务已停止（PID 7484）」 |
| **管理器/实例解耦** | kill 后 `node:7484` 仍在、3081 仍监听 | ✅ 管理器被杀，服务照常运行 |
| 重启后重新接管 | `t13_after_restart.png` | ✅ 重新识别仍在运行的实例：PID 7484、端口 3081、「运行中」 |
| 删除实例（确认框） | `s12_delete.png` | ✅ 确认提示完整：「删除实例「dsh-new」？…会先停止服务，然后删除整个目录并从登记表移除，不可恢复」 |
| 删除流程（旧版 2.0.19） | 实测 | ❌ BUG-6：停服务成功，但目录只删了一部分（剩 `app/pnpm-store/tools` 834MB），登记表已清空 |
| **删除流程（2.0.23 复验）** | `k01_card.png`、`k04_confirm.png`、`k05_deleted.png` | ✅ 造一个含 **42 个文件、其中 41 个只读、含 pnpm-store 深路径** 的登记实例，点删除 → 确认 → **目录彻底消失**（`Test-Path=False`）、`instances` 目录清空、`instances.json` 变 `[]`，底部提示「✓ 已删除实例目录」 |

### 内置会话窗口（WebView2）

| 项目 | 证据 | 结果 |
| --- | --- | --- |
| 打开窗口 | `t11_window.png`、`t12_webui.png` | ✅ 加载实例首页 → Preview Notice → Continue → DSH 主界面 |
| 按版本分流注入 | `web.log` | ✅ `preview profile: dsh=0.2.2-rc.1 -> modern(>=0.2)`，注入 `image-pan` + `file-dragout` |
| 独立数据目录 | `t12_webui.png` | ✅ 新实例显示「Sign in / Add an API Key」——`dsh-home` 全新，未继承任何凭据/工作区 |
| **窗口功能开关生效** | `s05_toggled.png`、`settings.json`、`web.log` | ✅ 关掉「放大后拖动平移」→ `settings.json` 写 `WebPan:false`；重开窗口后 `web.log` 只注入 `file-dragout`，**不再注入 `image-pan`** |
| 窗口功能窗口 | `f04_features.png`、`s04_features.png` | ✅ 两个开关 + 说明 + 关闭，主题一致 |

### 检查更新

| 项目 | 证据 | 结果 |
| --- | --- | --- |
| 打开更新窗口 | `s09_update.png` | ✅ 标题「更新 dsh」；显示实例、当前 dsh / Node 版本与来源 |
| 版本列表联网加载 | 同上 | ✅ dsh「共 3 个可选版本」、Node「共 79 个可选版本」，首项均为「保持当前（…）」 |
| 按钮 | 同上 | ✅ 检查更新 / 取消 / 应用 |

---

## 二、缺陷清单（VM 实测发现 → 修复进度）

| ID | 现象 | 根因 | 状态 |
| --- | --- | --- | --- |
| BUG-1 | 无 Git 的干净系统上创建实例 → `git clone 失败：An error occurred trying to start process 'git'…` | 直接起 `git` 子进程，没有预检 | ✅ 2.0.18：先 `git --version`，失败提示「请先安装 Git for Windows」 |
| BUG-2 | 安装失败后留下半成品目录，同名目录无法重试 | 失败路径不清理 | ✅ 2.0.18：本次新建的目录失败时递归删除并记日志 |
| BUG-3 | 新建实例对话框底部「空框」 | 日志卡片被启动提示/版本列表的 `AppendLog` 点亮 | ✅ 2.0.19：只在 `_busy`（真正安装）时显示；VM 复测已消失 |
| BUG-4 | 改「实例名称」时安装目录不跟随 | `OnDirChanged` 把程序自身赋值当成用户编辑 | ✅ 2.0.20：`SetDirSilently()` + `_suppressDir` |
| BUG-5 | 服务约 21–25s 才就绪，界面却提示「服务没有在 20 秒内就绪」 | 等待仅 20s，且未区分「进程还在」与「进程退出」 | ✅ 2.0.21：放宽到 60s，失败文案区分两种情况 |
| BUG-6 | 删除实例：服务停了、登记表清了，目录只删一部分（剩 834MB） | `taskkill` 后 node 仍握有句柄，立刻 `Directory.Delete` 抛异常；无重试/只读清理 | ✅ 2.0.22 + 2.0.23：删除前等端口真正释放（≤15s）+ 清只读 + 多轮重试 + 长路径兜底；**2.0.23 用只读+深路径实例复验已删净**（「带运行中服务」的场景正在复验中） |
| OBS-1 | 删除失败后登记表已清空，残留目录成「孤儿」 | 删除失败仍继续清登记 | 待定：失败时保留登记以便重试，或在扫描时提示孤儿目录 |

## 三、未覆盖项（及原因）

- **图片 Ctrl+滚轮缩放 / 放大后拖动 / 文件·目录拖出**：VM 实例是空工作区（无图片、无文件树内容），
  WebView 内部手势需真实内容触发；能力已在注入日志与宿主机环境验证，观感层面待有真实内容的实例再验；
- **刷新按钮转圈与状态行文案**：需要动画过程，静态截图无法判定，留待人工/录屏确认；
- **BUG-1 修复复验**：VM 已装 Git，回归需再造无 Git 环境或用临时 PATH 屏蔽。

## 四、可复用的测试设施

- `tools/vm-do.ps1`：下发动作清单（`click / type / uiaid / win / shot / wheel / start / kill / ls / ps`）→ 取回 `res.txt` 与截图
- `vm-serve/agent.ps1`：VM 内常驻代理（交互会话、隐藏窗口）
- `tools/vm-ps.ps1`：上传脚本并取回 stdout（查文件/端口/日志很方便）
- 截图证据：`vm-report/`
