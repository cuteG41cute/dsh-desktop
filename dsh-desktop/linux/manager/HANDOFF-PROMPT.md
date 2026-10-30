# 任务：把 dsh-manager 的界面做到**像素级复刻**设计稿，并把每个功能/按钮都测一遍

> 你是跑在 Linux 虚拟机上的 DSH agent。本目录里同时有**设计稿**和**当前实现**，
> 你的目标是把实现改成与设计稿一致（像素级），然后**逐项测试功能**，最后交回
> 一份可安装的 deb + 一份测试报告。
>
> 先读完这一份文件再动手。里面写了：目标、环境、文件在哪、怎么跑、怎么截图比对、
> 哪些是 GTK3 的硬限制（别去追）、验收标准、以及必须交回什么。

---

## 0. 一句话目标

- **视觉**：7 套主题 × 日/夜，每一种状态下窗口截图都与 `design/references/` 里对应的
  参考图**在布局、间距、圆角、配色、字重、图标位置上一致**（允许因 GTK 渲染差异
  造成的 1~2px 偏差；不允许"看着像但不是"）。
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
├── PROMPT.md                  ← 本文件
├── README.md                  ← 快速索引（和本文件重复度低，可先扫一眼）
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
│   │   ├── design/            ← 设计稿副本（生成器读它）
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

## 6. GTK3 的硬限制（**别去追**，追不到）

| 设计稿里有的 | GTK3 的现状 | 正确做法 |
| --- | --- | --- |
| `backdrop-filter: blur()` 真毛玻璃 | **没有** | 用预渲染背景图（`backgrounds/*.png`）+ 半透明面板近似 |
| `transform: translateY(-2px)` hover 上浮 | **没有** | 用 `box-shadow` 变化表达"抬起" |
| flex / grid 布局 | **没有** | 用 `Gtk.Box`/`Gtk.Grid` + CSS 的 padding/margin |
| CSS 变量 `var(--x)` | **没有** | 生成器把令牌**字面量**写进 CSS |
| `GtkLabel` 有背景色 | **没有** | 用 `Gtk.EventBox`（代码里已有 `_chip()` 专门干这个） |
| 渐变角度/多重阴影 | 支持，但写法挑剔 | `linear-gradient(135deg, a, b)`、`box-shadow: x y blur rgba(...)` |
| `font-weight: 550/680` | 只有 normal/bold | 生成器已归一为 bold/normal，别改回去 |
| 平滑滚动/弹簧动画 | 没有 | `transition` 只支持颜色/背景/边框/阴影，已用上 |

⚠️ **主题 CSS 是"全有或全无"**：GTK3 遇到一处非法值会**丢弃整个文件**，
界面退回默认皮肤（我们踩过：`@define-color` 里写了 `121,104,232` 就全裸奔）。
所以：任何改动都要靠 `theme-token-check.py` 兜底，别凭感觉。

---

## 7. 功能测试（这是硬要求：**每一个**都要过一遍并记录）

用下面这张矩阵逐项测试，把"操作 / 期望 / 实际 / 结论"写进 `REPORT.md`。
**测试要在**装好你自己构建的 deb、并且窗口是**重开过**的状态下做。

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
- 危险操作（卸载）有二次确认

---

## 9. 交付物（交回到共享盘 `~/share/`）

1. `dsh-manager_<版本>_all.deb` —— 用 `bash tools/vm-verify.sh` 构建，报告里写
   **大小 + sha256 + 包内主题/背景文件数（应为 29）**；
2. `REPORT.md` ——
   - 视觉：14 个状态（7 主题 × 日/夜）各一张截图 + 与参考图的**分区**比对结论；
     不一致处列出"参考值 → 实际值 → 改动点"；
   - 功能：上面 40 项矩阵逐行填（操作/期望/实际/结论）；
   - 已知限制：明确写出哪些是 GTK3 做不到的（从 §6 抄，可补）；
   - 变更清单：改了哪些文件、版本号、gate 结果；
3. `shots/` —— 全部截图（命名 `<主题>-<日/夜>-<区域>.png`）；
4. 若改了源码：**在 `REPORT.md` 里贴关键 diff 片段**（VM 上没有 GitHub 凭据，
   正式推送由我这边做，所以别尝试 `git push`）。

---

## 10. 工作纪律

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
