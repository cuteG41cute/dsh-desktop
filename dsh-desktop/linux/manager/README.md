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
| **打开窗口** | 先确保服务在跑，再用该实例的 `bin/dsh-desktop` 开 GTK 窗口（预览增强／右键保存／拖拽都在里面）；启动器输出写进 `<实例>/logs/desktop.log`，起不来会直接把原因回报到日志面板 |
| **更新版本** | 换 dsh 版本或 Node 版本（同样有 `latest`）；只动这个实例的目录 |
| **修复** | 补齐缺失的 Node / dsh / 窗口文件 / 启动器，补跑被 npm 11 拦下的 install scripts，校验目录可写 |
| **卸载** | 二次确认后删整个实例目录（含 Node、dsh 与实例的 dsh-home） |
| 在文件管理器中显示 | `xdg-open <实例目录>` |
| 日志 | 底部实时显示安装/更新/修复的每一步 |
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
| 按钮 | 按「服务 / 版本 / 其他」三组排列；主操作（启动服务、新建实例）深色实心，卸载单独标红 |
| 日志 | 独立卡片 + 等宽字体，圆角边框 |

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
