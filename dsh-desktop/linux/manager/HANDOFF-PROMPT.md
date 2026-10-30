# 任务：把 dsh-manager 的界面做到**像素级复刻**设计稿，并把每个功能/按钮都测一遍

> 你是跑在 Linux 虚拟机上的 DSH agent。本目录里同时有**设计稿**和**当前实现**，
> 你的目标是把实现改成与设计稿一致（像素级），然后**逐项测试功能**，最后交回
> 一份可安装的 deb + 一份测试报告。
>
> 先读完这一份文件再动手。里面写了：目标、环境、文件在哪、怎么跑、怎么截图比对、
> **每个效果怎么真的做出来（含需要的依赖）**、验收标准、以及必须交回什么。
>
> 态度上请**尽量都试**：这份文档不给"做不到"的结论，只给"怎么做"的路子；
> 真试不出来再记录原因（§6.7）。目标是让我们看看这套 GTK 界面能逼近设计稿到什么程度。

---

## 0. 一句话目标

- **视觉**：7 套主题 × 日/夜，每一种状态下窗口截图都与 `design/references/` 里对应的
  参考图**在布局、间距、圆角、配色、字重、图标位置上一致**。先按像素目标做（1~2px 内），
  做不到的地方记录原因与试过的手段（§6.7）。**鼓励把 §6 的方案都试一遍**——
  包括自绘模糊、cairo 位移、SVG 图标、字体替换，甚至另开 GTK4 实验分支。
- **功能**：界面上**每一个**按钮/菜单项/输入控件都能用，且行为符合设计意图；
  不允许出现"点了没反应""报错弹窗""状态不刷新"。
- **交付**：`dsh-manager_<版本>_all.deb`（可安装）+ `REPORT.md`（视觉对照 +
  功能测试矩阵 + 已知限制）。

---

## 1. 环境（已确认，不用再探测）

| 项 | 值 |
| --- | --- |
| 系统 | Ubuntu 26.04，KDE Plasma，**Wayland**（`XDG_SESSION_TYPE=wayland`） |
| 屏幕 | 1280×720（设计稿画布是 1440×900 —— 小屏上会紧凑，属正常） |
| GPU | `/dev/dri` 存在但 GL 不可用（Mesa `ZINK: failed to choose pdev`）→ 管理器/桌面壳会自动走软件渲染 |
| Python / GTK | 3.14.x / GTK 3.24.x（`python3-gi`、`gir1.2-gtk-3.0`） |
| 已装实例 | `~/Program/deepseek-harness-1`（端口 3080）、`~/.local/opt/deepseek-harness-2`（3081） |

**必装的两个工具**（截图与像素比对，当前机器上没有）：

```bash
sudo apt update && sudo apt install -y spectacle imagemagick python3-pil
```

`spectacle` 用于截窗口（Wayland 下只有它能截；`import`/`scrot` 在 Wayland 截不到），
`imagemagick`（`compare`/`convert`）+ `PIL` 用于比对与标注。

---

## 2. 目录结构（本包）

```
dsh-manager-ui-redesign/
├── PROMPT.md                  ← 本文件（任务书）
├── README.md                  ← 快速索引（和本文件重复度低，可先扫一眼）
├── KICKOFF.txt                ← 贴给会话的开场提示词
├── design/                    ← **设计稿原件**（Kimi 做的）
│   ├── index.html             ← 结构（侧栏 / 顶栏 / 仪表盘 / 设置页 / 弹窗 / toast）
│   ├── styles.css             ← 全部样式 + 7 套主题的令牌（唯一色值来源）
│   ├── app.js                 ← 交互（主题切换、日夜、菜单、弹窗、toast）
│   └── references/            ← **逐主题参考图**（像素比对就靠它们）
│       ├── 00-all-themes-overview.png
│       └── 01-frost-day.png … 07-sea-night.png   （7 主题 × 日/夜 = 14 张）
├── project/dsh-desktop/linux/ ← **当前实现**（就是你要改的东西）
│   ├── dsh-desktop / dsh-desktop.py    ← 桌面壳（GTK + WebKitGTK）
│   ├── manager/
│   │   ├── dsh_manager/       ← 管理器本体
│   │   │   ├── gui.py         ← 界面（**主要战场**）
│   │   │   ├── core.py        ← 实例/进程/窗口/版本/主题设置
│   │   │   ├── cli.py         ← 命令行
│   │   │   ├── themes.json    ← 从设计稿抽出的 14 组 × 25 个令牌
│   │   │   ├── theme/         ← 14 份生成好的 GTK 主题 CSS（**不要手改**）
│   │   │   └── backgrounds/   ← 14 张背景图（**不要手改**）
│   │   ├── INTERACTION.md     ← **每个按键的功能、状态与动效规格**（改交互前必读）
│   ├── design/            ← 设计稿副本（生成器读它）
│   │   ├── tools/             ← 生成器 + 全部 gate（见 §5）
│   │   └── build-deb.sh       ← 构建 deb
│   └── tools/                 ← 桌面壳侧 gate + 诊断脚本
└── tools/vm-verify.sh         ← 一键：跑全部 gate + 构建 deb + 打印 sha256
```

---

## 3. 先把基线跑起来（动手前必做）

```bash
cd ~/share/dsh-manager-ui-redesign          # 或你解包的位置

# 1) 全部 gate + 构建，确认基线是绿的
bash tools/vm-verify.sh

# 2) 装当前版本，看一眼现状
cd project/dsh-desktop/linux/manager && bash build-deb.sh
sudo dpkg -i dsh-manager_*_all.deb        # 或 bash ~/share/install-deb.sh
dsh-manager &                             # 打开管理器

# 3) 截图（Wayland 下用 spectacle）
spectacle -b -n -o /tmp/shot-now.png
```

**注意**：装完 deb 后必须**关掉管理器窗口再重开**，否则跑的还是内存里的旧代码
（这个坑我们踩过多次）。

---

## 4. 视觉复刻怎么做（工作流，照这个来）

1. **逐主题截图**：把管理器切到某主题/日或夜 → `spectacle -b -n -o /tmp/x-frost-day.png`。
   切主题：顶栏右侧「毛玻璃 ▾」菜单；切日夜：它右边那个 ☀/☾ 按钮。
2. **与参考图对齐比较**：参考图是 1440×900 的浏览器渲染；你的窗口在 1280×720 上，
   所以先**等比缩放参考图**到窗口客户区大小再比，或统一缩放到同宽。
   ```bash
   # 例：把参考图缩到与截图同宽，再并排/差分
   convert design/references/01-frost-day.png -resize $(identify -format %w /tmp/x-frost-day.png)x /tmp/ref.png
   compare -metric AE /tmp/ref.png /tmp/x-frost-day.png /tmp/diff.png 2>&1
   ```
3. **分区检查**（比整图更像"像素级"的做法）：按下面 8 个区域逐块裁切比对，逐块通过：
   - A 侧栏品牌区（logo 方块 / 标题 / 版本行）
   - B 我的实例（标题+计数+加号 / 实例行：头像、名称、版本、状态点 / 选中态）
   - C 新建实例按钮 + 工作空间三行 + 运行环境卡
   - D 顶栏（面包屑 / 主题按钮 / 日夜按钮 / ⓘ）
   - E 页面标题区（eyebrow / h1 / 状态徽标 / 描述 / 打开窗口 + ⋯）
   - F 两张卡（实例信息：大 avatar、路径、版本胶囊、三个指标 + 竖分隔线；快捷控制：两组按钮）
   - G 常用功能 4 格 + 最近日志卡（表头、等级胶囊、时间、空态）
   - H 设置页（信息列表 / 维护按钮 / 外观卡）
4. **改哪里**：
   - 间距/颜色/圆角/字号 → 改 `project/dsh-desktop/linux/manager/tools/gtk-theme-template.css.in`
     （这是**唯一**该手改的样式文件），然后重新生成 14 份主题：
     `python3 project/dsh-desktop/linux/manager/tools/build-gtk-theme.py`
   - 结构/控件/文案 → 改 `project/dsh-desktop/linux/manager/dsh_manager/gui.py`
   - 若发现设计稿里某个令牌没被用上（或值不对）→ 改
     `tools/extract-themes.py`（解析逻辑）或直接用设计稿里的值补进模板
   - **绝对不要**手改 `dsh_manager/theme/*.css` 和 `backgrounds/*.png`（它们由生成器
     和 `tools/render-backgrounds.mjs` 产出，改了会在下次生成时被覆盖，且 gate 会红）
5. 改完**必跑** `bash tools/vm-verify.sh`，红了先修红。

---

## 5. 已有的 gate（别删、别改断言，坏了要修）

| 脚本 | 检查什么 | 期望 |
| --- | --- | --- |
| `manager/tools/theme-token-check.py` | 设计稿 ↔ themes.json ↔ 14 份 CSS ↔ 背景图逐项一致；`@define-color` 的值必须是颜色；必须有 `transition`；不许出现 GTK3 不支持的写法 | 5/5 |
| `manager/tools/gui-import-check.py` | 桩 GTK 下真实构造 `ManagerWindow()`（抓解包/参数错），结构锁（侧栏/顶栏/Stack/主题菜单/快捷入口/日志卡/设置页…） | 35/35 |
| `manager/tools/ctl-protocol-check.py` | 管理器 ↔ 窗口控制协议（ping/raise/repaint/reload、唤起后补 repaint） | 10/10 |
| `manager/tools/token-extract-check.py` | 「查看 Token」：日志里取最新入口地址 + 200/401/连不上判定 | 11/11 |
| `manager/tools/check-picker.sh` | 版本选择器（真实 GTK，需图形环境） | 6/6 |
| `linux/tools/screenshot-bridge-check.py` | 桌面壳原生截屏桥（portal）+ 插件侧协议 | 14/14 |
| `linux/tools/socket-name-check.py` | 多实例：控制套接字/单锁按端口区分 | 13/13 |
| `linux/tools/gl-detect-check.py` | 软件渲染判据（虚拟 GPU → 关合成） | 12/12 |
| `linux/tools/gi-scope-check.py` | 模块级函数必须自己 import gi 名字 | OK |

**新增检查是加分项**：如果你修了某个像素问题，最好顺手加一条能防复发的断言
（尤其是"某个 class 必须存在/某个色值必须来自令牌"这类静态检查）。

---

## 6. 效果攻坚手册：设计稿里的每个效果，怎么在 GTK 里真的做出来

**原则：能试的都试。** 下面每一条都先给"为什么常规写法不行"，再给**可行的实现路子和依赖**。
只有在你实际试过并记录了失败原因之后，才允许在报告里写"这个效果没做到"——并且要写清
"试了什么、卡在哪、需要什么依赖或上游修复"。

先装这批依赖（按需，装了不会坏事）：

```bash
sudo apt update
sudo apt install -y \
    spectacle imagemagick python3-pil python3-numpy \
    python3-cairo python3-gi-cairo \
    librsvg2-common fonts-inter fonts-noto-cjk fonts-dejavu-core \
    gtk-3-examples accerciser xdotool wmctrl
```

| 装的东西 | 用来干什么 |
| --- | --- |
| `spectacle` | Wayland 下截窗口（唯一稳的） |
| `imagemagick` / `python3-pil` / `python3-numpy` | 像素比对、逐区域 RMSE、模糊/合成 |
| `python3-cairo` + `python3-gi-cairo` | 自绘（模糊面板、位移、渐变、圆角路径） |
| `librsvg2-common` | **加载设计稿里的 SVG 图标**（现在用的 Unicode 字符必然不像） |
| `fonts-inter` / `fonts-noto-cjk` | 设计稿是 Segoe UI/YaHei；Inter 是与它最接近的开源替代 |
| `gtk-3-examples` | `gtk3-demo`：现场试验 widget 能力 |
| `accerciser` | 查看真实控件树 / 确认某个控件有没有背景节点 |

### 6.1 真毛玻璃（模糊背景）——**可以做**

常规写法不行是因为 GTK3 没有 `backdrop-filter`。但我们的背景是**预渲染的静态 PNG**，
于是"模糊"完全可以自己算：

1. 子类化一个 `Gtk.EventBox`（或在 `draw` 里接管绘制）；
2. 用 `widget.translate_coordinates(win, 0, 0)` 拿到控件在窗口里的位置和尺寸；
3. 从 `backgrounds/<主题>-<日/夜>.png` 裁出**同一区域**（按窗口尺寸等比缩放对齐）；
4. 用 PIL/numpy 做高斯模糊（半径取设计稿的 `blur` 值：22~28px），**按（主题,尺寸）缓存**；
5. 用 cairo 画圆角矩形路径 → `set_source_surface(blurred)` → `paint()` → 再叠一层主题色
   半透明（`rgba(255,255,255,.25)` 之类）。

```python
# 骨架（放在 gui.py 的通用组件里）
import cairo, numpy as np
from gi.repository import Gdk, GdkPixbuf, Gtk
from PIL import Image, ImageFilter

_blur_cache = {}

def _blurred_surface(theme_key, win_size, alloc, radius):
    key = (theme_key, win_size, alloc, radius)
    if key in _blur_cache:
        return _blur_cache[key]
    # 1) 背景图按窗口尺寸缩放 → 2) 裁剪 → 3) 模糊 → 4) 转 cairo surface
    ...

class GlassBox(Gtk.EventBox):
    radius = 20
    def do_draw(self, cr):
        surface = _blurred_surface(...)
        cr.new_sub_path()
        cr.arc(...)   # 圆角矩形路径
        cr.set_source_surface(surface, 0, 0)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.25)
        cr.fill()
```

- 实测注意：`do_draw` 里不要做重活；模糊一定缓存（320×200 一次约几毫秒，但每帧都做会卡）。
- 备选：`Gdk.pixbuf_get_from_window()` 抓像素再模糊——X11 可行，**Wayland 下抓不到**，所以
  优先用"从背景图裁"的方案（背景本来就是我们自己渲染的，等价且稳定）。

### 6.2 transform（hover 上浮 / 缩放 / 位移动画）——**可以做**

GTK3 CSS 没有 `transform`，但绘制层有完整的 cairo 变换：

1. 在控件的 `draw`（或 `Gtk.DrawingArea` 的 `draw`）里 `cr.translate(0, -dy)`，自己画底和阴影；
2. 用 `GLib.timeout_add(16, …)` 跑 160ms 的插值（`ease-out`：`1-(1-t)^3`），更新 `dy` 后
   `queue_draw()`；
3. 鼠标进出用 `enter-notify-event` / `leave-notify-event`（或 CSS `:hover` 设个类切换）。

```python
def _animate(widget, start, end, ms=160, on_frame=None):
    t0 = time.time()
    def step():
        t = min(1.0, (time.time() - t0) * 1000 / ms)
        e = 1 - (1 - t) ** 3                     # ease-out
        on_frame(start + (end - start) * e)
        widget.queue_draw()
        return t < 1.0
    GLib.timeout_add(16, step)
```

- 更省事的近似：动画 `margin-top`（真位移但会触发重排，只在小卡片上试），或用
  `Gtk.Fixed` + `move()`（重排代价小）。
- 如果还想更接近：GTK4 有真 `transform` 与部分 `filter`，可以**另开一个实验分支**试
  GTK4 + libadwaita（管理器是独立进程，不影响桌面壳用的 GTK3/WebKitGTK 4.1）。
  决定前先确保现有 gate 全绿、且能回滚。

### 6.3 设计稿的 SVG 图标 ——**应该做，收益最大**

现在用的是 Unicode 字符替代（`⚙ ☾ ▤ …`），形状和线宽必然和设计稿不一样。
设计稿 `index.html` 里有 24 个 `<symbol>`，直接导出成独立 SVG 就能 1:1：

```bash
# 1) 从 index.html 抽出每个 <symbol id="i-xxx">…</symbol>，包成
#    <svg xmlns=... viewBox="0 0 24 24" fill="none" stroke="currentColor"
#         stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">…</svg>
#    存到 manager/dsh_manager/icons/i-xxx.svg（写个 20 行脚本即可，可复用）
# 2) 代码里替换 _label(glyph) 为：
img = Gtk.Image.new_from_pixbuf(
    GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 16, 16, True))
```

- 颜色：SVG 用 `stroke="currentColor"` 时 GdkPixbuf 不解析 CSS 颜色 → 两种做法：
  ① 生成两套（浅色 `#747288` / 深色 `#aaa6bb`）分别给日/夜；② 用 `Gtk.Image` 的
  `mask`/`style` 重新着色（`Gtk.Image#set_from_surface` + cairo 着色）。
- 这一步做完，图标区域的像素差异会立刻小一大截。

### 6.4 字体对齐 ——**应该做**

```bash
fc-match "Segoe UI"        # 会回退到 DejaVu，字形/字宽都不一样
sudo apt install -y fonts-inter fonts-noto-cjk
# CSS 里改成：font-family: "Inter", "Noto Sans CJK SC", "DejaVu Sans", sans-serif;
```

装完用 `fc-match Inter` 确认命中；再按截图微调 `font-size`（可写小数，如 11.5px）与
`letter-spacing`（GTK3 的 CSS 对 `letter-spacing` 支持不稳，若报错就去掉，改用文本对比）。

### 6.5 主题切换的"过渡" ——**可以试**

CSS 无法 crossfade 两套主题，但可以：切换前用 `Gdk.pixbuf_get_from_window`（X11）或
`Gtk.Widget.draw` 到 `cairo_surface` 抓一张当前窗口快照 → 放到 `Gtk.Overlay` 里的
`Gtk.Image` → 换主题 → 用 §6.2 的动画把快照 `opacity` 从 1 淡到 0（cairo
`set_source_surface` + `paint_with_alpha`）。能成就在报告里单独记一笔。

### 6.6 已经确认可用的 GTK3 能力（放心用）

- CSS：`border-radius` / `box-shadow`（含 `inset`）/ `linear-gradient(<angle>, …)` /
  `background-image: url()` / `background-size` / `transition`（颜色/背景/边框/阴影）/ `alpha()`
- 容器：`Gtk.Box`、`Gtk.Grid`、`Gtk.Stack`（含 SLIDE/CROSSFADE/OVER 等过渡）、
  `Gtk.Revealer`（多种滑动/淡入）、`Gtk.Paned`、`Gtk.FlowBox`、`Gtk.Overlay`
- 自绘：`Gtk.EventBox`/`Gtk.DrawingArea` 的 `draw` 信号给的是完整 cairo 上下文（变换、
  裁剪、模糊后的位图、渐变全都行）
- 动画调度：`GLib.timeout_add(16, …)` 跑 60fps 插值；`Gtk.ProgressBar.pulse()` 做脉冲

### 6.7 真做不到时怎么写报告

允许结论是"这一步没做到"，但必须**三件事齐全**：

1. 试过的方案（代码片段/命令）；
2. 失败的具体症状（报错原文、截图、崩溃栈）；
3. 需要什么才能做到（缺哪个依赖/需要 GTK4/需要上游修复的那个 issue）。

不许写"GTK 不支持所以跳过了"——那不是结论，那是没试完。

---

## 7. 功能测试（这是硬要求：**每一个**都要过一遍并记录）

用下面这张矩阵逐项测试，把"操作 / 期望 / 实际 / 结论"写进 `REPORT.md`。
**测试要在**装好你自己构建的 deb、并且窗口是**重开过**的状态下做。

**先读 project/dsh-desktop/linux/manager/INTERACTION.md** —— 那里写清了每个按键
「点了会发生什么 / 有哪些状态 / 动效时长与属性 / 对应代码位置」。下面这张矩阵是
它的可执行版；两者不一致时以 INTERACTION.md 为准，并顺手把矩阵补上。

### A. 侧栏
1. 点实例行 → 右侧卡片全部切到该实例（标题、徽标、路径、版本胶囊、PID、端口、状态）
2. 选中态：浅底 + 内边框 + 头像渐变（**不是**系统蓝/青）
3. 实例行状态点：运行中=绿；已停止=灰
4. 「我的实例」计数 = 实际实例数
5. 「＋」与「＋ 新建实例」→ 都打开新建对话框

### B. 新建实例对话框
6. 目录可浏览（浏览…）、名称随目录变
7. 端口默认取第一个空闲
8. **dsh 版本**：下拉框点开有预设项（latest + 5 个内置）；选一个值会改
9. **「更新」按钮**：点了会联网刷新并**覆盖**列表；失败不影响已有列表
10. **手动输入框**：输入版本号后 get_value 取手动值（优先级最高）
11. Node 版本同上
12. 取消 → 无副作用；创建 → 进度条脉冲、日志有步骤、完成后自动刷新列表

### C. 顶部动作 + 快捷控制
13. 「打开窗口」：已有窗口→提到前台并补 repaint；没有→启动；失败有明确日志
14. 「⋯」菜单：查看 Token / 重建窗口 / 在文件管理器中显示 / 卸载实例（分隔线）
15. 「启动」：停止态可用、运行态禁用；「停止」相反
16. 「重载」：窗口 reload（旧窗口应提示"没响应 reload"）
17. 「重建」：杀窗口+清锁+重开，服务/会话不动

### D. 常用功能 4 格
18. 查看 Token → 日志里出现带 token 地址 + 复制到剪贴板 + HTTP 状态说明
19. 管理插件… → 插件对话框：列出目录、安装/卸载可用（能装上/能卸掉）
20. 检查更新 → 版本选择对话框 → 更新后实例版本变化
21. 数据目录 → 文件管理器打开该前缀

### E. 顶栏
22. 主题菜单：7 项都在、点了立即换肤、当前项有勾选态、菜单自动收起
23. 日夜按钮：切换即时生效、按钮文字/图标随之变
24. 「ⓘ」→ 关于（版本/目录/运行环境）

### F. 侧栏底部
25. 实例概览 / 管理器设置：两页切换（面包屑同步、选中态同步）
26. 使用帮助：弹出帮助内容
27. 运行环境卡显示 Python/GTK 版本

### G. 设置页
28. 信息卡：版本/程序目录/配置目录/运行环境/实例根目录（可选中复制）
29. 查看管理器日志（本次运行 + 已落盘两段）
30. 复制诊断信息 → 剪贴板有内容 + toast
31. 修复 / 重装 → 走 repair 流程
32. 外观卡：「更换主题」循环切、日志行数保存后生效
33. 保存设置 → toast「设置已保存」，重开管理器后仍保持

### H. 日志与反馈
34. 最近日志：最多 3 条、新的在上、等级胶囊颜色（成功绿/失败红/系统灰）
35. 空态显示「还没有日志」
36. toast 出现后 2.6 秒自动消失
37. 查看完整日志：对话框文字区**填满**窗口（不能只有两行）

### I. 稳定性
38. 关掉管理器重开：主题/模式/日志行数保持
39. 同时开两个实例的窗口：**两个窗口**都能出来（不是只把第一个提前）
40. 关窗口再开：不残留锁、不重复进程（`ps aux | grep dsh-desktop`）

**每一项都要留证据**：截图（`/tmp/` 下）或命令行输出。测试不通过就修，修完重测。

---

## 8. 交互与动效（容易被忽略，单独确认）

- 按钮/链接/实例行/快捷卡 hover 有 160ms 过渡（颜色/边框/阴影）
- 主题切换有 Stack 的 crossfade / toast 有 SLIDE_UP
- 忙碌时：顶部脉冲进度条出现，所有操作按钮禁用（避免并发）
- 上面这些 160ms 过渡 / crossfade / SLIDE_UP 是**当前已实现**的；设计稿里还有更强的动效
  （模糊、位移、主题交叉淡入），按 §6 的方案去试，成了就同步更新 INTERACTION.md 与本节
- 危险操作（卸载）有二次确认

---

## 9. 交付物（交回到共享盘 `~/share/`）

1. `dsh-manager_<版本>_all.deb` —— 用 `bash tools/vm-verify.sh` 构建，报告里写
   **大小 + sha256 + 包内主题/背景文件数（应为 29）**；
2. `REPORT.md` ——
   - 视觉：14 个状态（7 主题 × 日/夜）各一张截图 + 与参考图的**分区**比对结论；
     不一致处列出"参考值 → 实际值 → 改动点"；
   - 功能：上面 40 项矩阵逐行填（操作/期望/实际/结论）；
   - 效果攻坚记录：逐个列出设计稿里非常规的效果（毛玻璃 / 位移 / SVG 图标 / 字体 / 主题过渡），写清**试了什么、结果如何、最终采用哪种实现**；没成功的按 §6.7 三件事写全；
   - 变更清单：改了哪些文件、版本号、gate 结果；
3. `shots/` —— 全部截图（命名 `<主题>-<日/夜>-<区域>.png`）；
4. 若改了源码：**在 `REPORT.md` 里贴关键 diff 片段**（VM 上没有 GitHub 凭据，
   正式推送由我这边做，所以别尝试 `git push`）。

---

## 10. 工作纪律

- **鼓励实验**：§6 里的方案都可以试点；实验性改动放独立分支/独立文件，
  保证随时能退回（gate 绿 + 能构建 = 可回滚）。别因为"难"就不试。
- **一次只改一件事**，改完立刻 `bash tools/vm-verify.sh`；红了先修红再往下。
- **不要**为了"看起来像"去硬编码像素值到 `gui.py`（间距应写在 CSS 模板里）。
- **不要**手改生成物（`theme/`、`backgrounds/`、`themes.json` 里 `values` 段）。
- 若某项功能本来就坏（不是样式问题）：先**记录**再修，别顺手大改（会掩盖原有 bug）。
- 遇到 GTK 报错：`dsh-manager` 的 stderr 会写进终端 / `~/.config/dsh-manager/manager.log`；
  主题加载失败会显示「✘ 主题未加载：原因」——按原因改，不要绕过。
- 版本号：改完功能/样式后 `core.py` 的 `MANAGER_VERSION`、`build-deb.sh`、
  `deb/DEBIAN/control` 三处一起 bump（例如 1.3.2 → 1.3.3）。

---

## 11. 起手式（照抄即可）

```bash
cd ~/share/dsh-manager-ui-redesign
sudo apt update && sudo apt install -y spectacle imagemagick python3-pil
bash tools/vm-verify.sh                       # 基线必须 PASS

# 现状截图（7 主题 × 日/夜都截一遍，作为"改前"证据）
mkdir -p /tmp/before
for t in frost liquid crystal flat alpine dawn sea; do
  for m in day night; do :; done
done
# （主题/日夜通过顶栏按钮切换；每次切换后）
spectacle -b -n -o /tmp/before/frost-day.png

# 然后按 §4 逐区域比对 → 改模板 → 重新生成 → 再跑 gate → 再截图
```

开工。做完把 `REPORT.md` 和 deb 放到 `~/share/`，我这边负责把改动合进仓库并发布。
