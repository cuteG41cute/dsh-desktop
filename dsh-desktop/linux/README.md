# DeepSeek Harness 桌面版 —— Linux（deepin / Ubuntu / Debian）

GTK3 + WebKitGTK 原生窗口，**功能与 Windows 版对齐**，并且是**便携安装**：
Node、dsh、pnpm、数据目录全都放在你指定的那一个目录里，不往系统里装任何东西。

## 1. 安装（一条命令）

```bash
cd dsh-desktop/linux
bash install.sh --prefix "$HOME/.local/opt/deepseek-harness"
```

* 安装位置可以随便指定（`--prefix /opt/dsh`、U 盘上的目录都行）；
* 自带 **便携 Node**（解压到 `<前缀>/node`），**不做全局 npm 安装**；
* `@deepseek-ai/dsh` 与 `pnpm` 装进 `<前缀>/app`、`<前缀>/tools`；
* 数据目录默认 `<前缀>/dsh-home`（`DSH_HOME`），**不动你的 `~/.dsh`**；
* 卸载 = 删掉那一个目录：

```bash
bash install.sh --prefix "$HOME/.local/opt/deepseek-harness" --uninstall
```

### 目录结构

```
<前缀>/
├─ bin/dsh               # 命令行：只用前缀里的 node 与包
├─ bin/dsh-desktop       # 图形窗口（应用菜单里也是它）
├─ node/                 # 便携 Node（官方 tarball 解压）
├─ app/                  # @deepseek-ai/dsh（package.json + node_modules）
├─ tools/                # pnpm（只有 dsh plugin 子命令会用到）
├─ share/                # dsh-desktop.py / 启动器 / preview-tools.js / 图标
├─ dsh-home/             # DSH_HOME：profiles、storages、凭据
├─ logs/web.log          # 服务的 stdout/stderr
└─ install.json          # 安装记录（版本、路径、时间）
```

### 系统里仍然需要的（无法便携化）

| 依赖 | 用途 | 安装 |
| --- | --- | --- |
| `python3` + `python3-gi` | 窗口进程 | `sudo apt install python3 python3-gi` |
| `gir1.2-gtk-3.0` | 窗口 UI | `sudo apt install gir1.2-gtk-3.0` |
| `gir1.2-webkit2-4.1`（或 `-4.0`） | 页面内核 | `sudo apt install gir1.2-webkit2-4.1` |
| `curl`/`wget`、`tar`、`xz` | 下载/解压 Node | 系统自带 |

安装器会先检查这些并打印确切的 apt 命令；缺 GUI 库时它仍然会把 Node/dsh 装好（只是窗口打不开），
装完依赖再跑一次即可。

### 离线安装

```bash
bash install.sh --prefix /opt/dsh \
  --node-tarball ~/node-v24.19.0-linux-x64.tar.xz \
  --dsh-tarball  ~/deepseek-ai-dsh-0.1.5-rc.1.tgz
```

## 2. 功能对照（与 Windows 版）

| 能力 | 实现方式 | 状态 |
| --- | --- | --- |
| 预览缩放（图片滚轮 15%–800%）/ 拖动平移 / 加粗滑动条 | **同一份** `preview-tools.js` 注入 | ✅ |
| PDF：Ctrl+滚轮全局缩放、可超出显示区域、100% 精确 | 同上（PDF 独立分支） | ✅ |
| 预览右键菜单：保存到… / 复制图片 / 复制文件路径 / 在文件管理器中显示 / 缩放项 | `preview-tools.js` + 宿主消息 | ✅ |
| 保存弹**原生对话框，默认「桌面」**，逐字节复制原文件 | GTK `FileChooserDialog` | ✅ |
| 复制图片（位图 + 文件 URI） | GTK 剪贴板（`set_with_data`） | ✅ |
| 在文件管理器中显示 | `org.freedesktop.FileManager1` → 退回 `xdg-open` | ✅ |
| 拖出去保存（文件树行 / 交付卡 → 文件管理器） | WebKit **原生 HTML5 拖拽** `text/uri-list` | ✅ |
| 拖进输入框（文件→待发送附件、文件夹→路径文字） | 页面 drop + 宿主 `dsh-read-file` | ✅ |
| 会话拖拽分离窗口、多窗口、标题镜像、`window.open` | GTK 窗口管理 + 注入脚本 | ✅ |
| 单实例、托盘、加载进度、Web 认证 cookie | 启动器 flock + `Gtk.StatusIcon` + HMAC 签发 | ✅ |

> 与 Windows 的唯一结构差异：Windows 上「拖出」由宿主发原生 OLE 拖放（`DoDragDrop`）；
> Linux 上改用 WebKit 自己的 HTML5 拖拽（`dragstart` 里写 `text/uri-list`/`text/plain`），
> 因为 GTK 侧「用合成事件启动拖放」不可靠。注入脚本里用 `IS_WEBKIT` 分流，其余逻辑完全共用。

## 3. 使用

```bash
<前缀>/bin/dsh-desktop            # 打开窗口（服务没在跑会自动拉起）
<前缀>/bin/dsh-desktop --setup    # 只做依赖检查，不开窗口
<前缀>/bin/dsh web                # 纯命令行：起服务
python3 <前缀>/share/dsh-desktop.py --selftest   # 自检：服务 / cookie / 注入 / 运行时 / GTK
```

* 主窗口按 X = 收进托盘（托盘里「显示窗口 / 退出」）；分离出来的子窗口按 X 直接关；
* 关掉最后一个窗口时，如果服务是它启动的，会一并停掉；
* 环境变量：`DSH_WEB_URL`、`DSH_HOME`、`DSH_PREFIX`、`DSH_SHARE`、`DSH_DESKTOP_NO_SERVICE=1`、
  `DSH_DESKTOP_AUTH_COOKIE`、`DSH_DRAG_DEBUG_LOG`。

## 4. 已验证 / 待验证

**已实测（WSL2 · Deepin 23.1 · 便携 Node 24.19 · 从 npm 装 522 个包）**

| 检查 | 结果 |
| --- | --- |
| 便携安装（默认前缀） | ✅ Node 解压、dsh 装进前缀、pnpm 装进 tools、启动器与 `install.json` 齐全（约 523 MB） |
| 幂等（重复安装） | ✅ 复用已有 Node 与同一版本 dsh |
| 卸载 | ✅ 只删前缀目录，系统无残留（全程没有 `npm -g`） |
| `bin/dsh web` 在 Linux 上起服务 | ✅ 7 秒内监听，返回 **401 + `dsh web: …?token=` URL**，自动生成 `profiles/`、`storages/`、`.credentials.yaml` |
| cookie 签发（与两个启动器同一算法） | ✅ 用真实 `.credentials.yaml` 跑通，171 字节 |
| `preview-tools.js` 与 Windows 共用 | ✅ Windows 侧回归：拖拽 12/12、右键菜单 30/30 |

### 用浏览器打开（不是桌面窗口）

桌面窗口自己会签发认证 cookie，所以它从来不问；**浏览器里直接敲 `http://127.0.0.1:3080`
只会看到一张 401 提示页**：

```
dsh web authentication required; reopen the URL printed by dsh web.
```

正确的入口是 `dsh web` 启动时打印的那条地址（`http://127.0.0.1:3080/?token=…`），
打开一次后服务端种下 cookie，同一个浏览器之后就能直接用裸地址。不用自己翻日志：

```bash
bash dsh-desktop/linux/tools/open-web.sh           # 找地址 → 验证 → 打开浏览器
bash dsh-desktop/linux/tools/open-web.sh --print   # 只打印地址（复制到别的浏览器）
```

它从 `<前缀>/logs/{web,server.out,server.err,desktop}.log` 与
`~/.local/state/dsh-desktop/logs/` 里挑**最新**一条 `dsh web: …?token=`，
先请求一次确认返回 200（401 说明 token 过期 → 重启服务再跑；连不上说明服务没起），
再交给 `xdg-open`。自测：`bash dsh-desktop/linux/tools/open-web-selftest.sh`（造假日志，5 项）。

**待在你的 Ubuntu 上验证**（WSL 里没有 python3/WebKitGTK，且 sudo 需要密码，装不了）

1. `bash install.sh --prefix ~/.local/opt/deepseek-harness` → 自检是否全绿；
2. `<前缀>/bin/dsh-desktop` → 窗口能否打开、预览缩放手感；
3. 预览右键 →「保存到…」→ 是否弹原生对话框、默认在桌面、落盘是否原样；
4. 右栏文件树的行走拖到文件管理器 → 是否复制过去；拖进输入框 → 文件夹是否变路径；
5. 会话拖出侧边栏 → 是否开新窗口。

把任何一步的输出/现象发我，按现象修。
