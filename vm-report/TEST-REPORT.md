# dsh-manager Windows · 虚拟机实测报告

测试环境：Hyper-V「Windows 11 开发环境」`WINDEV2407EVAL`（Windows 11 Enterprise Evaluation，Build 22621.3880，1024×768）
接入方式：`ssh User@172.30.26.56`（OpenSSH，公钥）+ 会话内**常驻代理**（读 `req.txt` 执行动作、写 `res.txt`、可随时截屏）
被测版本：2.0.17 → 2.0.19（测试过程中按缺陷迭代）

---

## ✅ 通过项（均有截图或日志证据）

| # | 项目 | 证据 | 说明 |
| --- | --- | --- | --- |
| 1 | 干净系统安装 | `install-win.ps1` | 装到 `%LOCALAPPDATA%\Programs\DSH Manager` |
| 2 | 首次启动 / 空状态 | `t01_main219.png` | 「未发现 DSH 安装」，扫描位置列全，四角圆角正常 |
| 3 | 新建实例对话框 | `t02_dialog.png` | 五字段可编辑；默认目录自动生成 |
| 4 | **目录校验** | `d03_guard.png` | 指向已存在目录 → 「目录已存在且不为空，请换一个目录」，不开始安装 |
| 5 | **源码安装全流程** | `t04_started.png`、`t08_done.png` | `git clone` → 实例内 pnpm → `pnpm install` → `pnpm run build` → 生成 `dsh-home`，全程 ~22 分钟（VM 内） |
| 6 | 实例卡片 | `t08_done.png` | 标题=目录名 `dsh-new`，dsh `0.2.2-rc.1`、Node `27.0.0-alpha.0`、端口 3081、状态「未运行」 |
| 7 | **启动服务** | `t10_running.png` | 点「启动」→ 状态「运行中」，**PID 7484**、端口 **3081**，按钮变「停止」，快捷控制「服务正常」 |
| 8 | 服务真实监听 | `logs\<id>.log` | `dsh web: http://127.0.0.1:3081/?token=…`，`Get-NetTCPConnection 3081` 有监听 |
| 9 | **打开窗口** | `t11_window.png`、`t12_webui.png` | WebView2 加载实例首页；「Preview Notice」→ Continue → DSH 主界面 |
| 10 | 按版本分流注入 | `web.log` | `preview profile: dsh=0.2.2-rc.1 -> modern(>=0.2)`；`image-pan injected`、`file-dragout injected` |
| 11 | 独立数据目录 | `t12_webui.png` | 新实例显示「Sign in… Add an API Key」——`dsh-home` 全新，未继承任何凭据/工作区 |
| 12 | **管理器/实例解耦** | `agent kill` → `port3081=3`、`node:7484` 仍在 | 杀掉管理器后服务照常运行 |
| 13 | **重启后重新接管** | `t13_after_restart.png` | 管理器重启后识别出仍在运行的实例：PID 7484、端口 3081、「运行中」 |
| 14 | 窗口功能窗口 | `f04_features.png` | 两个开关 + 说明 + 关闭，主题一致 |
| 15 | 托盘/单实例 | 实测 | 关闭窗口后进程仍在托盘；再次启动 exe 可把窗口叫回来 |

## 🐞 发现并修复的缺陷

| ID | 现象 | 根因 | 修复 |
| --- | --- | --- | --- |
| BUG-1 | 无 Git 的干净系统上创建实例 → 状态行是 `git clone 失败：An error occurred trying to start process 'git'…` | 直接起 `git` 子进程，没有预检 | 2.0.18：`OnCreate` 先跑 `git --version`（8s 超时），失败提示「请先安装 Git for Windows」 |
| BUG-2 | 安装失败后在实例目录留下 `node\` 半成品，导致同目录无法重试 | 失败路径没有清理 | 2.0.18：本次新建的目录在失败时递归删除并记日志 |
| BUG-3 | 新建实例对话框底部一块「空框」 | 日志卡片被启动提示/版本列表加载的 `AppendLog` 点亮，但没有实质内容 | 2.0.18 去掉启动提示；**2.0.19 改为仅 `_busy`（真正在安装）时才显示** —— VM 复测已确认空框消失（`t02_dialog.png`） |
| BUG-4 | 改「实例名称」时安装目录不跟随 | `OnDirChanged` 把程序自己的赋值也当成「用户手动编辑」，`_dirEdited` 被提前置位 | 2.0.20：新增 `SetDirSilently()` + `_suppressDir`，程序赋值不触发标记；浏览选择仍视为手动 |
| BUG-5 | 服务已在 ~20s 内就绪，底部仍出现「服务没有在 20 秒内就绪…」类提示 | 就绪等待窗口偏短/提示过早 | 待修（记录中） |

## ⏳ 待测（下一轮）

- 「停止」服务后端口释放、状态回到未运行；
- 「删除实例」（停服务 → 删目录 → 移出列表）；
- 「窗口功能」开关关闭后重载 → `web.log` 应不再注入对应脚本；
- 图片 `Ctrl+滚轮` 缩放、放大后拖动平移、文件/目录拖出（需要在页面里构造出图片与文件树场景）；
- 「检查更新」窗口：立刻弹出、转圈、版本列表、只有一处「当前」；
- 实例卡片「刷新」转圈与状态行文案。

## 测试基础设施（可复用）

- `tools/vm-do.ps1`：写动作清单到 VM 的 `req.txt`，等代理执行后取回 `res.txt` 与截图
- `vm-serve/agent.ps1`：VM 内常驻代理（click / dclick / type / uiaid / win / shot / kill / start / ls / ps / del）
- `tools/vm-ps.ps1`：上传脚本并直接取回 stdout
- 截图证据目录：`vm-report/`
