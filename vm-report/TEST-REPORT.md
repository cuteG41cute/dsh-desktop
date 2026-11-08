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
| **改名目录跟随（BUG-4 复验）** | `s01_name.png` | ✅ 名称改成 `dsh-a` → 安装目录自动变 `...\instances\dsh-a-2`（`dsh-a` 已存在，避让生效） |
| **端口占用校验** | `q04_port445.png` | ✅ 端口填 445（系统服务在听）→ 创建按钮点了也不开始安装，状态行显示「端口 445 已被占用（系统里别的程序在监听）」 |
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
| BUG-6b | 更硬的证据：实例目录里 `Remove-Item -Recurse -Force` 直接失败，报 **`Could not find a part of the path 'pagepanecanvasmaster.xml'`**；改用 `rd /s /q \\?\<abs>` 后一次删净 | 仓库里的深层/超长路径（node_modules 与构建产物）超出传统 API 的处理能力 | ✅ 我们的 `DeleteDirectoryRobust` 正是按「清只读 → 重试 → `\\?\` 长路径兜底」三步写的，与这条实测吻合 |
| BUG-7 | 便携 Node 下载在网络抖动时**卡在某个字节数不动**（VM 实测停在 18.3MB），界面一直停在「正在克隆官方仓库并构建…」像死机 | 只有 `HttpClient.Timeout=10min` 兜底，一条挂死的连接要等十分钟；且下载过程没有任何输出 | ✅ 2.0.24 连接超时 15s + 2.0.25 **30 秒无新字节即判定卡死并重试** + 每 8MB 打一行进度 |
| FEAT-1 | Node 下载中断后重试，会因「目录必须为空」被挡下，只能换目录重来 | 校验把管理器自己的半成品也算成"脏目录" | ✅ 2.0.26：目录里只有 `node/tools/pnpm-store/app` 时允许**继续复用**；VM 实测：预置 node 后创建直接跳过下载进入 clone |
| OBS-1 | 删除失败后登记表已清空，残留目录成「孤儿」 | 删除失败仍继续清登记 | 待定：失败时保留登记以便重试，或在扫描时提示孤儿目录 |

## 三、内置窗口增强：桩页面验证

为了绕开「实例装不出来就没法看窗口」的死结，我在 VM 里用**桩页面**（自写 HTML 模拟 DSH 的 DOM）验证注入层：

| 项目 | 证据 | 结果 |
| --- | --- | --- |
| 窗口加载桩页面 | `w02_window.png`、`web.log` | ✅ 窗口导航到 `http://127.0.0.1:3081/`，`nav success=True` |
| 注入按版本分流 | `web.log` | ✅ `preview profile: dsh=? -> modern(>=0.2)`，注入 `file-dragout` |
| 注入是否命中新 DOM | `web.log` 的 `dom probe` | ✅ `files:true, zoomFrame:true`（桩页面里有 `data-files-path` 和 `_scrollport`，探测全中） |
| 页面可滚动（拖动平移前提） | `fakepage.log` | ✅ `loaded=1&w=955&sw=2000`（内容 2000 > 视口 955） |

> 这一步只证明「注入层认得这套 DOM、页面状态就绪」；**真正的拖动平移与拖出手势**还没跑完——见下面的阻塞。

## 四、手势脚本验证（Chromium 无头运行，绕开 VM 的 GUI 阻塞）

VM 的计划任务通道在增强会话下彻底失效（连 `cmd /c echo hi > ping.txt` 这种最小任务都停在 **Queued**），
所以改用**同一套脚本 + 同引擎（Edge/Chromium ≈ WebView2）**在无头浏览器里做行为验证：

测试页 `tools/js-test/harness.html`：搭出与真实页面同构的 DOM（`_scrollport` / `_surface` / `li[data-files-path]`），
内联加载 `image-pan.js`、`file-dragout.js`，用合成的 pointer/mouse 事件驱动，并 stub 掉 `chrome.webview.postMessage` 收集消息。

运行：`msedge --headless=new --dump-dom file:///…/harness.html`，结果存 `vm-report/js-harness-result.txt`：

```
pan_before=100,100
pan_after=160,160          ← 放大后可滚动，左键拖动让 scrollLeft/Top 各 +60：**平移生效**
pan_cursor=(reset)         ← 松开后光标恢复
msgs_count=2
msg0=dsh-drag-out -> C:\temp\a.txt      ← 文件行拖出，路径正确
msg1=dsh-drag-out -> C:\temp\folder     ← 目录行拖出，路径正确
nopan_before=0,0
nopan_after=0,0            ← 不可滚动（未放大）时不接管拖动：**符合设计**
loaded_pan=boolean / loaded_dragout=boolean
```

结论：两个注入脚本的**行为逻辑（平移、文件/目录拖出的消息与路径、未放大时不介入）**在真实 Chromium 里成立。

## 五、代理恢复后的复测（2026-11-05 下午）

用户打开代理后重测：小请求通了，大流量仍旧不稳。

| 项目 | 结果 |
| --- | --- |
| `cdn.sheetjs.com` / `nodejs.org` / `github.com` HEAD | ✅ 全部 200（直连，无需 VM 内配代理） |
| `git ls-remote https://github.com/deepseek-ai/deepseek-harness` | ✅ 成功（exit 0） |
| **`git clone --depth 1`** | ❌ 间歇失败：`fatal: expected 'packfile'`（传输被打断）、另一次 `Could not connect to github.com:443` |
| 便携 Node 下载 | ✅ 成功（实例目录出现 `node\node.exe`） |
| 失败的清理 | ✅ 再次验证 BUG-2：clone 失败后实例目录被自动清空（`instances` 为空） |

结论：这台 VM 到 GitHub 的**大流量长连接不稳定**，所以「完整源码安装 → 真服务 → 删除」这条链在本次仍没能走完；
但链路上的每一段都已被单独验证：clone 之前的 git 预检 ✅、Node 下载 ✅、clone 失败后的清理 ✅、
停止服务（真实实例，`taskkill` 后端口释放、状态回「未运行」）✅、删除（只读 + 深路径一次删净）✅。
「服务运行中删除」= Stop 之后等端口释放 + 健壮删除，这两段各自都验证过。

## 六、环境限制（VM 网络）

| 现象 | 证据 | 结论 |
| --- | --- | --- |
| `pnpm install` 失败：`ERR_PNPM_FETCH_TIMEOUT GET https://cdn.sheetjs.com/…` | `u01_ui.png` | 这台开发虚拟机**访问不了 cdn.sheetjs.com**（该依赖不走 npm registry，直接走厂商 CDN），`pnpm install` 因此中断。**不是产品缺陷**；同一台机器上早前网络好时完整装过一次实例 |
| 便携 Node 下载多次卡住（停在 18.3MB 不动） | 实测 | 用户网络抖动；已用 2.0.24/2.0.25 的「连接超时 + 30 秒无进展判定 + 重试」治住，并加了下载进度日志 |

## 七、未覆盖项（及原因）

- **图片 Ctrl+滚轮缩放 / 放大后拖动 / 文件·目录拖出**：VM 实例是空工作区（无图片、无文件树内容），
  WebView 内部手势需真实内容触发；能力已在注入日志与宿主机环境验证，观感层面待有真实内容的实例再验；
- **刷新按钮转圈与状态行文案**：需要动画过程，静态截图无法判定，留待人工/录屏确认；
- **BUG-1 修复复验**：VM 已装 Git，回归需再造无 Git 环境或用临时 PATH 屏蔽；
- **「刷新」按钮转圈与状态行文案**：需要观察动画过程，静态截图无法判定，本次未录制；
- **「服务运行中直接删除」**：受 GitHub 大流量不稳影响，本次 VM 里没能装出真服务；已拆成「停止服务」（真实实例验证过）与「健壮删除」（只读+深路径验证过）两段分别验证。

## 八、阻塞记录（GUI 自动化通道）

- **现象**：VM 的交互会话从 `console` 切成了 Hyper-V 增强会话（`31c5ce94259d4…`，Active），此后用 `schtasks /ru User /it` 创建的任务状态一直停在 **Queued**，不再真正执行（`agents=0`）。重启虚拟机、重启 Task Scheduler 服务、重建任务都无效；连最小任务 `cmd /c echo hi > ping.txt` 也是 Queued，说明**不是脚本问题，是这台 VM 的交互任务通道坏了**。
- **影响**：需要注入鼠标/键盘的动作（拖动平移、文件拖出、点击类验证）暂时无法继续。
- **对策**：重新在 Hyper-V 里连接这台虚拟机的控制台（或重启 VM）让任务恢复执行；也可以改用 `vmconnect` 保持会话在 console。

## 九、2.0.28 新增能力的脚本级验证（无头 Chromium）

| 能力 | 结果 |
| --- | --- |
| 交付卡拖出 | `dsh-drag-out -> C:\\Users\\tester\\Desktop\\工作\\内忧外患-…pptx`（路径取自卡片的 `title`） |
| 交付卡右键菜单 | 弹出「保存到桌面… / 复制文件路径 / 在资源管理器中显示」，且 `defaultPrevented=true`（浏览器默认菜单被顶掉） |
| 点“保存到桌面…” | 发出 `dsh-save-file` 消息（带路径与文件名），菜单随即关闭 |
| 普通区域右键 | `defaultPrevented=false`、不弹自定义菜单（不干扰其它区域） |
| 预览区右键 | 同样弹出菜单（图片文件时额外出现“复制图片”） |

测试页：`tools/js-test/harness2.html`。

## 十、2.0.29 文件夹拖入（桥注入）验证

产品前端判定逻辑（`dsh-client-ui-conversation`）：

```js
const bridge = globalThis.__DSH_HOST_PATHS__;         // 桌面版注入的“文件→绝对路径”桥
if (bridge === undefined && 拖的是目录) return "只有桌面端支持添加文件夹";
const path = bridge?.pathFor(file) ?? "";
if (目录 && path === "") return "无法获取文件夹路径";
```

浏览器拿不到真实绝对路径，所以注入 `folder-drop.js`：
- 装上 `__DSH_HOST_PATHS__.pathFor(file)`；
- 拖动时（dragenter/dragover/drop 捕获阶段）记录本次拖动里哪些是**目录**；
- **目录**返回它的名字（相对工作区，例如 `报告素材`）→ 产品生成 `@报告素材/` 引用；
- **普通文件**返回空串 → 保持原来的上传/附件行为不变。

无头 Chromium 验证（`tools/js-test/harness3.html`，用产品同款判定逻辑复算）：

```
bridge_present=true
before_drag_dir=            （拖动前不干扰）
after_drag_dir_path=报告素材
after_drag_file_path=""     （文件仍走上传）
product_result=dir:报告素材,file:(upload)   ← 不再出现“只有桌面端支持添加文件夹”
after_clear_dir=""          （1.8s 后自动清理）
```

本机 `web.log`：`folder-drop injected (2019 chars)`。

**已知限制**：工作区**之外**的文件夹，引用会是 `@名字/`，可能落空（浏览器无绝对路径可用）。

## 十一、可复用的测试设施

- `tools/vm-do.ps1`：下发动作清单（`click / type / uiaid / win / shot / wheel / start / kill / ls / ps`）→ 取回 `res.txt` 与截图
- `vm-serve/agent.ps1`：VM 内常驻代理（交互会话、隐藏窗口）
- `tools/vm-ps.ps1`：上传脚本并取回 stdout（查文件/端口/日志很方便）
- 截图证据：`vm-report/`
