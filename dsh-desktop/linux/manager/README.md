# DeepSeek Harness 管理器（dsh-manager）

一个图形界面，管**多个** DeepSeek Harness 实例：装、更新、修复、卸载、启停、打开窗口。
每个实例自带便携 Node 与 dsh，互不影响，也不向系统安装任何东西。

## 1. 安装（.deb）

```bash
sudo apt install ./dsh-manager_1.0.0_all.deb     # apt 会自动装 python3-gi / GTK 依赖
# 或者
sudo dpkg -i dsh-manager_1.0.0_all.deb && sudo apt -f install
```

装完从应用菜单打开 **「DeepSeek Harness 管理器」**，或命令行 `dsh-manager`。

> 依赖：`python3` `python3-gi` `gir1.2-gtk-3.0`（Depends）；
> **打开桌面窗口**还需要 `gir1.2-webkit2-4.1`（或 `-4.0`，Recommends）—— 没装也能装管理器，只是窗口打不开。

自己构建：

```bash
cd dsh-desktop/linux/manager
bash build-deb.sh --version 1.0.0        # 产出 ./dsh-manager_1.0.0_all.deb
```

## 2. 界面能做什么

| 操作 | 说明 |
| --- | --- |
| **＋ 新建实例** | 选安装目录、显示名、端口、dsh 版本、Node 版本；端口默认取第一个空闲（避免多开冲突）。版本默认 **`latest`**＝最新的非 alpha 版本（由管理器联网解析；rc 算，alpha 不算） |
| **启动服务 / 停止服务** | 后台跑 `dsh web --no-open --port <端口>`，PID 记在 `<实例>/logs/web.pid` |
| **打开窗口** | 先确保服务在跑，再唤起/启动该实例的 GTK 窗口：**已有窗口就提到前台**；没有则清理僵死窗口进程与旧锁，失败时自动用「强制 + 软件渲染」重试。实例里的窗口程序与本包不一致时会**顺手对齐**，不用先点修复。启动器输出写进 `<实例>/logs/desktop.log` |
| **重载页面**（1.1.3 起） | 向窗口进程发 `reload`，让它重新加载页面。页面里的脚本把布局搞坏（比如浮层卡住、整块空白）时，这是最小的动作，不影响服务与会话 |
| **重建窗口**（1.1.3 起） | 窗口**进程还活着、但画面已经坏了**（软件渲染下最常见的「上半截空白」）时，唤起是修不好的：这一项会结束窗口进程、清掉 `/tmp/dsh-desktop.lock*`、重新起一个，**服务与会话都不动**（窗口里没发出去的输入会丢） |
| **查看 Token**（1.1.5 起） | 把当前实例的 **WebUI 入口地址（带 token）**显示在下方日志框里，并顺手复制到剪贴板。浏览器里直接敲 `http://127.0.0.1:3080` 只会看到 401「authentication required」，必须用这条带 token 的地址；打开一次后服务端种 cookie，同一浏览器之后就能用裸地址。地址从 `<实例>/logs/{web,server.out,server.err,desktop}.log` 和 `~/.local/state/dsh-desktop/logs/` 里取**最新**一条（大日志只读尾部 256 KB），并先请求一次告诉你状态：200 可用 / 401 已过期（服务重启过）/ 连不上（服务没在跑）。**token 等价于密码：只显示在界面上，不写 manager.log** |
| **更新版本** | 换 dsh 版本或 Node 版本（同样有 `latest`）；只动这个实例的目录 |
| **修复** | 补齐缺失的 Node / dsh / 窗口文件 / 启动器，补跑被 npm 11 拦下的 install scripts，校验目录可写 |
| **卸载** | 二次确认后删整个实例目录（含 Node、dsh 与实例的 dsh-home） |
| 在文件管理器中显示 | `xdg-open <实例目录>` |
| **管理插件…** | 从我们自己的 GitHub 仓库给这个实例安装 / 卸载插件（见下节） |
| 日志 | 底部实时显示安装/更新/修复/装插件的每一步 |
| 忙碌进度条 | 安装/更新/修复期间顶部出现的脉冲进度条（不确定进度，类似 Win7 的滚动光条）；版本列表在后台联网获取，界面不会冻结 |

版本选择器是滚动的列表（`Gtk.MenuButton + Popover + ScrolledWindow + ListBox`）——GTK 自带
`Gtk.ComboBox` 的菜单式下拉在长列表上滚不动，所以没有用它。打开「新建实例」时对话框立刻可用，
可以先点「安装」用 `latest`，也可以在版本列表拉回来之后再挑具体版本。

### 外观：企业简洁风主题（1.0.4 起）

界面套了一层 GTK CSS 主题（`dsh_manager/style.css`），与仓库里的介绍页
（`dsh-desktop/site/index.html`）使用同一套视觉语言：

| 元素 | 处理 |
| --- | --- |
| 配色 | 近白底 `#fbfbfa`、卡片纯白、细线 `#e6e3de`、墨色正文、单一藏青强调色 `#1f4e79` |
| 顶栏 | 白底 + 1px 下边线，右侧一枚版本药丸（`v1.0.4`） |
| 列表 | 卡片式容器 + 扁平表头，行选中用浅蓝底，**状态列带彩色圆点**（绿=运行中 / 黄=已停止 / 红=需修复 / 蓝=端口有服务） |
| 详情 | 标题旁的状态徽标 + 信息卡（键灰、值墨），路径可选中复制 |
| 按钮 | 按「服务 / 窗口 / 版本 / 插件 / 其他」分组排列；主操作（启动服务、新建实例）深色实心，卸载单独标红 |
| 日志 | 独立卡片 + 等宽字体，圆角边框 |

### 小屏上「看不到底」（1.1.6 修）

1280×720 的屏幕上，默认窗口比屏幕还高，加上右侧五组按钮把日志挤到窗口外——
**最后一组按钮和日志框根本点不到**。现在这么处理：

| 改动 | 做法 |
| --- | --- |
| 打开时尺寸不超出屏幕 | 按 `Gdk.Monitor.get_workarea()`（已扣掉面板/任务栏）算初始尺寸，留 60px 余量 |
| **窗口最小尺寸：不设** | 想缩多小自己拖。极限由内容决定（上部是滚动区、日志卡只留 64px 底高，整窗可以缩到 ~130px 高）；拖动窗口边缘随时能缩 |
| 上部可滚动 | 标题 / 信息卡 / 五组按钮放进 `Gtk.ScrolledWindow`（只纵向滚动），窗口再矮也够得着 |
| 日志可用但不占死高度 | 右侧是**竖直 `Gtk.Paned`**：默认给日志留约 200px，其余给按钮区；窗口变小后 GTK 自动收紧，分隔条可拖 |

这几条在 `tools/gui-import-check.py` 里钉成了结构锁（23 项），删掉任何一段都会红。

### 多实例：一个实例一套套接字与锁（1.1.7 修）

以前控制套接字是 `dsh-desktop-<uid>.sock`、单实例锁是 `/tmp/dsh-desktop.lock`，**全局唯一**。
结果是：开第二个实例的窗口时，管理器 ping 到的是**第一个实例**的窗口 → 判定"窗口已存在" →
只把第一个窗口提到前台，第二个实例的窗口根本没被创建（用户实测：两个实例只显示第一个）。

现在都按**实例端口**区分：

| 东西 | 现在 |
| --- | --- |
| 控制套接字 | `$XDG_RUNTIME_DIR/dsh-desktop-<uid>-<port>.sock` |
| 单实例锁 | `/tmp/dsh-desktop-<port>.lock`（`.pid` / `.lock.d` 同理） |
| 端口来源 | 管理器 `env()['DSH_DESKTOP_PORT']` + 启动器从 URL 推导并导出；窗口侧 `instance_port()` 同规则 |

一致性有 gate 钉着：`python dsh-desktop/linux/tools/socket-name-check.py`（13 项，含
「两个实例的套接字不同」「两侧命名完全一致」「清锁认按端口的锁名」）。

### 界面：按 Kimi 的设计稿复刻（1.3.0 起）

> 每个按键做什么、有哪些状态、动效是什么 —— 见 [INTERACTION.md](INTERACTION.md)。
> 改交互/验收前先读它。

设计稿在 `manager/design/`（`index.html` / `styles.css` / `app.js`，7 套主题 × 日/夜），
界面按它重做：**左侧实例栏**（品牌 / 我的实例 / 新建实例 / 工作空间 / 运行环境）、
**顶栏**（面包屑 / 主题选择 / 日夜切换）、**仪表盘**（标题+状态徽标 / 实例信息卡 /
快捷控制卡 / 常用功能 4 格 / 最近日志 3 行 / 页脚）、**管理器设置页**（信息 / 维护 / 外观）。

复刻不是"照着颜色抄一遍"，而是**从设计稿生成**：

| 环节 | 做法 |
| --- | --- |
| 令牌 | `tools/extract-themes.py` 解析 `design/styles.css` 的级联（`:root` → 夜间基础 → 主题 → 主题+夜间），得到 14 组 × 25 个令牌 → `dsh_manager/themes.json` |
| 主题 CSS | `tools/build-gtk-theme.py` 把令牌灌进 `tools/gtk-theme-template.css.in`，生成 `dsh_manager/theme/<主题>-<日/夜>.css`（含调色板 + 全部控件样式） |
| 背景 | `tools/render-backgrounds.mjs` 用无头 Chromium 渲染设计稿的 `.scene`（光斑 / 雪山 / 海浪 / 晨光 / 水晶），输出 14 张 PNG 到 `dsh_manager/backgrounds/` |
| 切换 | 顶栏「主题」菜单选 7 套之一、日/夜按钮切换；设置页也能换。选择存 `settings.json`（`theme` / `mode`），立即生效不用重启 |
| 保真核对 | `tools/theme-token-check.py`：设计稿 ↔ themes.json ↔ 14 份 CSS ↔ 背景图，逐项比对（色值、圆角、阴影、背景引用），5 项全过才算"复刻" |

GTK3 没有 `backdrop-filter` / CSS 变量 / flex：透明面板叠在**预渲染背景图**上，
布局用 GTK 容器表达，观感与设计稿一致而实现走 GTK 自己的路。

### 原生截屏桥（1.2.0 起，修 Linux Wayland 下截图必失败）

Linux 桌面壳（WebKitGTK）里点截图按钮只会转圈然后报错。根因不在插件与 DSH：

```
getDisplayMedia → xdg-desktop-portal(ScreenCast) → PipeWire → kwin      ← 这一段正常
                → WebKitGTK 用 GStreamer caps 协商接收画面             ← 死在这里
```

kwin 广播**可变帧率**（SPA EnumFormat `framerate=0/1`），WebKitGTK 2.52.6 协商时断言失败：

```
gst_value_collect_int_range: assertion 'collect_values[0].v_int < collect_values[1].v_int' failed
```

所以桌面壳改成**一次性拿整幅 PNG**，绕开视频流协商：

| 环节 | 实现 |
| --- | --- |
| 页面 → 壳 | `window.chrome.webview.postMessage({type:'dsh-screenshot', id})`（shim 早已提供） |
| 壳 → portal | `org.freedesktop.portal.Screenshot`，`interactive=false`（无对话框），**先订阅 Response 再调用**（否则竞态丢响应），`handle_token` 纯字母数字（带 `-` 会被 KDE 后端拒） |
| 壳 → 页面 | 读 `file://` → `data:image/png;base64,…` → `window.__dshShotReply(id, {ok, dataUrl})` |
| 页面 | `nativeCapture()` → canvas → 原有框选 / 标注 / 入附件（**零改动**） |
| 代价 | 一次 PNG 约 340 KB（1280×720），不占带宽流；30 秒兜底超时 |

配套的插件侧改动在 `dsh-screenshot` 1.3.1（`nativeCapture()` + 回退 + 命名坑修复）。
部署注意：**模板在 deb 里**（`/usr/lib/dsh-manager/share/dsh-desktop.py`），
管理器「打开窗口」时会把它同步到各实例的 `<实例>/share/`，所以不需要手工打补丁。

gate：`python dsh-desktop/linux/tools/screenshot-bridge-check.py`（14 项：真读文件转 data URL /
先订阅后调用 / 回传函数名 / 30 秒兜底 / 插件里原生通道排在 getDisplayMedia 之前 …）。

### 版本选择器改成原生下拉框（1.1.9 修）

用户反馈「点了选不了版本」。原来的选择器是 `Gtk.MenuButton` + 自定义 `Popover` +
`ListBox`（为了长列表能滚），在用户的 Wayland/KDE 桌面上点了没反应，且不好定位。
现在按用户的建议重做：

| 项 | 现在 |
| --- | --- |
| 控件 | **`Gtk.ComboBoxText`**（原生下拉，鼠标/键盘都能选），旁边一个手动输入框 |
| 预设列表 | 打开对话框就有：`latest` + 内置清单（dsh 5 项 / Node 4 项），不需要等联网 |
| **「更新」按钮** | 每个版本行右侧一个，点它联网拉最新列表，**新列表覆盖旧列表**；失败只改 tooltip，不破坏已有列表 |
| 手动输入 | 一直可用且**优先级最高**：列表不准/没网时直接打版本号 |
| 打开时 | 仍会自动后台拉一次（拉到就覆盖），所以不点按钮也能拿到最新 |

逻辑有 gate 钉着（`gui-import-check` 30 项，含「版本选择器用原生下拉框」「有预设列表与手动输入」
「有更新按钮且会覆盖旧列表」）。另外可以在目标机器上单跑一次真实 GTK 验证：

```bash
bash check-picker.sh        # 用已安装的 dsh_manager 真建一个 VersionPicker，检查 6 项
```

### 日志区高度按窗口百分比（1.1.8 修）

两个问题叠在一起：

| 问题 | 原因 | 现在 |
| --- | --- | --- |
| 「管理器日志」窗口里文字只有两行、下半截全空 | `Gtk.Box.add()` 等价于 `pack_start(child, False, False)`，**不伸展**，ScrolledWindow 只拿到自然高度（约两行） | 改成 `pack_start(sw, True, True, 0)`，文字区填满对话框 |
| 对话框 780×520 写死 | 小屏超出、大屏浪费 | `_dialog_size()` 按管理器窗口的 **72% 宽 / 80% 高**取，再夹进屏幕工作区 |
| 主窗口日志卡高度写死像素 | 窗口变大变小它不跟着变 | 日志占右侧高度的**比例**（默认 38%），`notify::position` 记住用户拖出来的比例，窗口尺寸变化时按比例重算 |

结构锁：`gui-import-check` 现在 26 项（含「日志高度按窗口百分比分配」「日志查看器会填满对话框」
「对话框尺寸按窗口百分比给」）。

### 版本列表拉不到时也能选（1.1.7 修）

原来 `latest_*` 与 `available_*` 各自拉一遍 registry 完整文档（2~3 MB，8 秒超时）；
冷启动那一次超时 → 列表只剩内置一项（`0.1.5-rc.1`）→ 用户体验就是「版本选不了」。现在：

- registry 结果**进程内缓存 5 分钟**，超时放宽到 25 秒，官方源失败自动切 `registry.npmmirror.com`；
- `latest` 只查 `…/@deepseek-ai%2Fdsh/latest`（几百字节，比拉全量快一个数量级）；
- 内置兜底清单从 1 项扩到 5 项（dsh）/ 4 项（Node）；
- 对话框里每个版本行右侧多一个**手动输入框**：列表不准或拉不到，直接打版本号即可。

### 插件管理（1.1.0 起，第一阶段）

右侧「插件」分组里的 **管理插件…**：列出一个内置目录（我们自己的仓库），
对**当前选中的实例**做安装 / 卸载，装完提示重启该实例的服务。

目录（仓库结构是实测核对过的）：

| id | 仓库 | 包所在目录 | 说明 |
| --- | --- | --- | --- |
| `dsh-time-stamp` | `cuteG41cute/dsh-time-stamp` | `static/` | 时间戳注入 |
| `dsh-memory-db` | `cuteG41cute/dsh-memory-db` | `static/` | 项目记忆库 |
| `dsh-screenshot` | `cuteG41cute/dsh-screenshot` | `static/` | 对话内截图与标注 |
| `dsh-netmon` | `cuteG41cute/dsh-mobile` | `netmon/` | 网络 / 隧道监视（**插件在手机项目仓库里**） |
| `dsh-api` | `cuteG41cute/dsh-api` | `plugin/` | HTTP 调用接口 |
| `dsh-file-history` | *（未发布）* | — | 改前自动备份 |
| `dsh-butler` | *（未发布）* | — | 管家派活通道 |
| `dsh-cleaner` | *（未发布）* | — | 会话 / 文件清理 |

**"装进一个实例"= 两件事**（与手工安装的结构完全一致）：

1. 包体复制到 `<实例>/dsh-home/profiles/web/node_modules/<包名>/`
2. 在 `<实例>/dsh-home/profiles/web/cordis.patch.yml` 里追加一条
   `- insert:` 记录（`id` / `name` / 可选 `inject`），前面带一行
   `# ── installed-by: dsh-manager (<id>) ──` 标记，卸载时按它精确摘除

**关于「覆盖不全」这件事**（1.1.2 起）：

- 一个仓库可以有多个包（`dsh-netmon` 就在 `cuteG41cute/dsh-mobile` 的 `netmon/` 下），
  所以目录里给每个插件写了 `subdir`；选包优先级是 **subdir 命中 > 带 `dsh` 字段 > 名字与 id 相同 > 浅层**；
- 实例 `node_modules` 里**任何 `dsh-*` 包都会列出来**（标「实例里已装，不在目录中」），
  哪怕它不是从这里装的——避免"看不见就以为没装"；
- 还没推 GitHub 的插件（`dsh-file-history` / `dsh-butler` / `dsh-cleaner`）在列表里显示「未发布」，
  点安装会明确告诉你「只能本地导入」；此时用 **导入本地包…** 选一个 `.tar.gz` 即可（包名取自 package.json）。


下载顺序（任一成功即用）：`api.github.com/.../tarball/<ref>` →
`codeload.github.com/...` → 本地缓存
`~/.cache/dsh-manager/plugin-cache/<id>-main.tar.gz`。
所以**完全离线也能装**：把 tarball 按这个名字放进缓存目录即可。
包里若有多个 `package.json`（根目录是动态版、`static/` 才是常驻版），按
「带 `dsh` 字段 > 名字与 id 相同 > 非 private」挑选，实测选中 `static/`。

命令行同源：

```bash
dsh-manager --headless plugins --prefix <实例目录> [--json]
dsh-manager --headless install-plugin   --prefix <实例目录> --id dsh-time-stamp
dsh-manager --headless uninstall-plugin --prefix <实例目录> --id dsh-time-stamp
```

已知边界（第一阶段）：不处理插件自己的 `settings.yaml` 配置段（例如 `dsh-api`
的 `apiKey`），装完需要按插件文档手动配；卸载不会删插件写进 `settings.yaml` 的配置；
插件依赖（npm 包）暂不自动 `npm install`。这些都留给第二阶段。
### 窗口唤起（1.0.8 起）

窗口进程在 `$XDG_RUNTIME_DIR/dsh-desktop-<uid>.sock` 上监听一个极简控制套接字
（纯文本一行，权限 0600）：

```
ping     → ok <pid>
raise    → 把窗口提到前台，回 raised
repaint  → 强制整窗重绘（改一次窗口尺寸再改回去 + invalidate），回 repainted
reload   → 重新加载页面，回 reloaded
quit     → 退出
```

于是「打开窗口」不再是"再起一个进程碰运气"：

1. **已有窗口** → 直接 `raise` 到前台，**顺手补一条 `repaint`**（这就是再点一次该有的行为）；
   软件渲染下窗口从托盘/最小化回来时，WebKit 可能只重绘局部，留下一条没画过的灰带，
   这条 `repaint` 会把整个后备存储作废重画；
2. **没有窗口但锁还在 / 有僵死进程**（旧版窗口没有控制套接字，只能被识别为僵死）→
   先 `SIGTERM` 再 `SIGKILL`，并删掉 `/tmp/dsh-desktop.lock*`；
3. **正常启动一次**，用套接字确认"窗口真的起来了"，而不是只看进程有没有退出；
4. **失败就采取措施**：加 `DSH_DESKTOP_FORCE=1`（跳过单实例检查）+ `DSH_DESKTOP_GL=off`
   （强制软件渲染）重试一次——Hyper-V 这类没有 `/dev/dri` 的环境窗口会"进程活着但界面出不来"；
5. 两次都失败才报错，并把 `logs/desktop.log` 末尾附上。

「重建窗口」走的是同一条 2→4 的路，但**即使套接字还活着也先杀**：画面坏了的时候，
`raise` 与 `repaint` 都救不回来，只能重开一个。命令行等价物：

```bash
dsh-manager --headless reload  --prefix <实例目录>   # 重载页面
dsh-manager --headless repaint --prefix <实例目录>   # 只重绘
dsh-manager --headless rebuild --prefix <实例目录>   # 重建窗口（也可 open --rebuild）
dsh-manager --headless token   --prefix <实例目录>   # 只打印带 token 的入口地址（标准输出）
```

窗口程序本身也加了兜底（1.1.4 起判据改对了）：`/dev/dri` **存在不等于 GL 可用**。
KVM / Hyper-V 虚拟机里 `/dev/dri` 常常是 `virtio_gpu`，Mesa 却选不到 pdev：

```
libEGL warning: failed to get driver name for fd -1
MESA: error: ZINK: failed to choose pdev
libEGL warning: egl: failed to create dri2 screen
```

这种机器如果走 GPU 路径，窗口就会只画出一部分（实测：上半截是一块没画过的灰板）。
现在两层拦截：

1. **启动器判据**：`/dev/dri` 不存在 **或** DRM 驱动是虚拟显卡
   （`virtio_gpu / vmwgfx / qxl / bochs / vboxvideo / vkms / simpledrm`）→
   自动 `WEBKIT_DISABLE_COMPOSITING_MODE=1` + `LIBGL_ALWAYS_SOFTWARE=1`；
   可用 `DSH_DESKTOP_GL=on|off` 覆盖、`DRM_DRIVER=<名字>` 直接指定驱动；
2. **窗口内 GL 探测**：创建 WebView **之前**用 GDK 真去建一次 GL 上下文，建不出来就
   立刻切软件渲染（环境变量只在 WebKit 初始化时读一次，所以必须在这之前）。

判据本身有 gate：`python dsh-desktop/linux/tools/gl-detect-check.py` 会把启动器里那段
判据原样剪出来、用假 sysfs 真跑 12 个用例（含 `virtio_gpu + /dev/dri 存在 → 软件渲染`）。
### 管理器设置（1.0.5 起）

顶栏右侧的齿轮按钮，专门管「管理器自己」：

| 项 | 内容 |
| --- | --- |
| 版本 / 路径 | 管理器版本、程序目录 `/usr/lib/dsh-manager`、配置目录、日志文件、Python 与 GTK 版本、实例根目录 |
| 外观 | 主题开关（写入 `~/.config/dsh-manager/settings.json`，重启生效）、日志面板保留行数 |
| 维护 | **查看管理器日志**（`manager.log`，日志面板里的每一行都会落盘，>512KB 轮转）、**复制诊断信息**（版本 + 路径 + 实例列表 + 最近日志，一次粘给排障的人）、**修复 / 重装…**、**卸载…**（都只给出命令 + 说明，管理器运行中不会去删自己） |

管理器装在哪、日志在哪、怎么备份配置，都在这个对话框里看得见 —— 不用再去翻源码猜。

**这是纯外观改动**：GTK 解析失败或被系统主题干扰时只会回落到默认皮肤，功能不受影响。
想直接关掉：`DSH_MANAGER_NO_THEME=1 dsh-manager`（或临时改掉 `style.css` 的名字）。


每个实例的目录结构（和 `linux/install.sh` 一致，管理器能直接接管用 install.sh 装过的实例）：

```
<实例目录>/
├─ bin/dsh, bin/dsh-desktop
├─ node/            # 便携 Node
├─ app/             # @deepseek-ai/dsh（package.json + node_modules）
├─ tools/           # pnpm（dsh plugin 用）
├─ share/           # dsh-desktop.py / 启动器 / preview-tools.js / 图标
├─ dsh-home/        # DSH_HOME（数据）
├─ logs/web.log, logs/web.pid
└─ install.json     # 名称、端口、版本、安装时间
```

管理器把实例登记在 `~/.config/dsh-manager/instances.json`，同时会**扫描** `~/.local/opt`
等目录下带 `app/package.json` 的前缀 —— 所以 `install.sh` 装过的实例也能在界面里看到并接管。

## 3. 命令行（同一套核心，便于脚本化/排障）

```bash
dsh-manager --headless list [--json]
dsh-manager --headless install --prefix ~/.local/opt/dsh-1 --dsh 0.1.5-rc.1 --port 3080 --label A
dsh-manager --headless start  --prefix ~/.local/opt/dsh-1
dsh-manager --headless status --prefix ~/.local/opt/dsh-1 --json
dsh-manager --headless stop   --prefix ~/.local/opt/dsh-1
dsh-manager --headless update --prefix ~/.local/opt/dsh-1 --dsh <版本> --node <版本>
dsh-manager --headless repair --prefix ~/.local/opt/dsh-1
dsh-manager --headless uninstall --prefix ~/.local/opt/dsh-1 --yes
dsh-manager --headless versions --kind dsh|node [--json]
```

环境变量：`DSH_MANAGER_ROOT`（新实例默认根目录，默认 `~/.local/opt`）、
`XDG_CONFIG_HOME`（注册表位置）、`DSH_MANAGER_VERBOSE=1`（把日志打到 stdout）。

## 4. 已验证 / 待验证

**已实测（WSL2 · Deepin 23.1 · 便携 Python 3.12 + 便携 Node 24.19）**

| 检查 | 结果 |
| --- | --- |
| 核心：新建实例（自选目录/端口/版本） | ✅ 装完 `install.json`、`bin/dsh`、`bin/dsh-desktop`、`share/`、`dsh-home/` 齐全 |
| 多开：两个实例不同端口 | ✅ 两个目录、两个端口各自起服务，互不干扰 |
| 启动 / 状态 / 停止 | ✅ 状态 JSON（running/stopped）、停止后端口不再监听 |
| 更新（同版本重装） | ✅ 幂等，不动数据目录 |
| 修复 | ✅ 补窗口文件与启动器、重写 install.json |
| 卸载 | ✅ 只删实例目录，注册表同步移除 |
| `.deb` 构建 | ✅ `dpkg-deb` 打包、`--info` / `--contents` / `-x` 解包核对通过 |

**待在你的 Ubuntu 上验证**：GUI 本身（WSL 里没有 python3-gi / GTK，且 sudo 需要密码装不了）。
界面上的操作都走同一套已被测过的核心，所以主要是看布局与交互是否顺手。
