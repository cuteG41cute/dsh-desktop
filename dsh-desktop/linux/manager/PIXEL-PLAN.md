# 像素级复刻设计稿：流水线与施工图

目标：让 GTK3 的 `dsh_manager` 界面与 `design/index.html` 逐像素对得上。
设计稿是可运行的 HTML/CSS，所以**设计稿本身就能出图**，比对完全可自动化。

## 1. 流水线（三段，全部可复跑）

```
design/index.html ──[design-shot.mjs]──> design/references/<主题>-<日/夜>-<页>.png   参考图
                    └[design-spec.mjs]──> design/references/spec-*.json               施工图（数字）
~/dsh-dev (GTK) ───[vm-gtk-shot.py]───> /tmp/gtk/<主题>-<日/夜>-<页>.png             实拍图
两者 ───────────────[diff-shots.py]───> MAE / 超阈值像素比 / 热力图 / 并排图
```

```powershell
# 1) 设计稿参考图（1440×900 画布 → .app-shell 裁出 1392×852）
node dsh-desktop\linux\manager\tools\design-shot.mjs            # 28 张
node dsh-desktop\linux\manager\tools\design-spec.mjs frost day dashboard

# 2) GTK 实拍（离屏，不需要合成器，任意尺寸）
tar -czf $env:TEMP\manager-dev.tgz -C dsh-desktop\linux\manager --exclude=__pycache__ dsh_manager
scp -P 22 $env:TEMP\manager-dev.tgz twinblade@172.22.148.197:/tmp/
powershell -File tools\host\vm.ps1 -Script tools\host\vm-push-dev.sh
powershell -File tools\host\vm.ps1 -Script tools\host\vm-gtk-shot.py -Args '/tmp/gtk','1392x852','frost:day','dashboard,settings' -Fetch /tmp/gtk/frost-day-dashboard.png

# 3) 比对
python tools\host\diff-shots.py dsh-desktop\linux\manager\design\references\frost-day-dashboard.png `
  vm-shots\frost-day-dashboard.png vm-shots\cmp
```

GTK 侧的关键技巧：`ManagerWindow` 的子控件搬进 `Gtk.OffscreenWindow` 再 `get_pixbuf()`，
所以 1432×892、1392×852 这种比屏幕（1280×720）还大的尺寸也能拍，且没有壁纸/标题栏干扰。
数据用 fixture（`tools/host/vm-gtk-shot.py` 里的 `DESIGN`）喂成设计稿里那一套：
dsh / deepseek-harness-1（运行中 PID 90837 端口 3080）/ deepseek-harness-2，外加 3 行日志。

## 2. 施工图（frost/day/dashboard，单位 px，相对 .app-shell）

| 元素 | x | y | w | h | 半径 | 内边距 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| shell | 0 | 0 | 1392 | 852 | 26 | 0 | 左上角圆角 26，边框 1px |
| sidebar | 1 | 1 | 248 | 850 | 0 | 26/16 | GTK 侧 `set_size_request(248)` 已对 |
| brand | 17 | 27 | 215 | 66 | – | 0/8 | 标记块 38×38 半径 12 |
| 实例列表 | 17 | 132 | 215 | 193 | – | 0 | 每行 215×61，行间距 5 |
| 实例行 | 17 | 132 | 215 | 61 | 13 | 8/10 | 头像 34×34 半径 10 |
| 新建实例 | 21 | 338 | 207 | 38 | 11 | 1/6 | 列表下方紧接 |
| 侧栏底部 | 17 | 594 | 215 | 239 | – | 24/0 | |
| 侧栏链接 | 17 | 640 | 215 | 40 | 10 | 0/11 | |
| 运行环境卡 | 21 | 777 | 207 | 56 | 12 | 13/10 | |
| main | 249 | 1 | 1142 | 850 | – | 0 | |
| topbar | 249 | 1 | 1142 | 66 | – | 0/30 | 背景 alpha 0.25 |
| content | 249 | 67 | 1142 | 784 | – | 25/30 | 内容左边 279 |
| page-heading | 279 | 92 | 1082 | 70.25 | – | 0 | h1 25px / 680 / 行高 31.25 |
| overview-grid | 279 | 184.25 | 1082 | 205 | – | 0 | 卡片间距 16 |
| 实例信息卡 | 279 | 184.25 | 663.73 | 205 | 20 | 18/20 | |
| 快捷控制卡 | 958.73 | 184.25 | 402.25 | 205 | 20 | 18/20 | |
| 快捷功能区 | 279 | 410.25 | 1082 | 109 | – | 0 | 与上一段间距 21 |
| 快捷按钮 | 279 | 437.25 | 262.25 | 82 | 15 | 13/13 | 4 列，列间距 22.67 |
| 快捷图标 | 293 | 461.25 | 34 | 34 | 10 | – | 底色 accent@0.1 |
| 日志卡 | 279 | 539.25 | 1082 | 144 | 20 | 0 | 表头 45，行 27 |
| 页脚 | 279 | 683.25 | 1082 | 23 | – | 12/2 | |

字号（px）：h1 25 / eyebrow 8 / card-label 11 / 侧栏链接 11.5 / breadcrumb 11 /
状态徽章 9 / 主按钮 11 / 日志行 8.5 / 头像 10（字重 750）。
配色示例（frost/day）：正文 `rgb(37,36,58)`、强调 `rgb(121,104,232)`、次要 `rgb(116,114,136)`、
卡片 `rgba(255,255,255,0.62)`、成功 `rgb(43,155,120)`。

## 3. 基线（2026-10-31 首次比对，frost/day/dashboard，1392×852）

| 指标 | 值 |
| --- | --- |
| MAE（0–255，越低越好） | **8.68** |
| 像素差 > 16 的占比 | 13.09% |
| 像素差 > 48 的占比 | 4.4% |
| 最差区块 | x 348–522（内容左列）、y 142–284（概览卡）、侧栏 0–348 |

热力图 `vm-shots/cmp2-diff.png`、并排图 `vm-shots/cmp2-side.png`。

## 4. 差距清单（按收益排序）

1. **图标全是 Unicode 字符**。设计稿有 27 个 24×24 描边图标（`<symbol id="i-*">`），
   GTK 侧用 `＋ ↗ ⓘ ▶ ▣ ⚒` 之类字符顶着 —— 这是目前最大的视觉差异。
   做法：抽出符号 → `dsh_manager/icons/<id>.svg`，运行时按主题色替换 `currentColor`
   再用 `GdkPixbuf.PixbufLoader` 载入（需要 gdk-pixbuf 的 svg loader，VM 上待确认）。
2. **字体不同**：设计稿 `"Segoe UI", "Microsoft YaHei UI"`（Windows 专有），
   虚拟机上是 `Noto Sans 10`。两条路：
   - 比对用「同一字体」：给 `design-shot.mjs` 加 `DSH_DESIGN_FONT` 覆盖成 Noto Sans，
     这样 diff 只反映布局/配色差异（推荐先这么做，否则每次都会被字宽差干扰）；
   - 真机观感：给 GTK 一份 Inter（`~/.local/share/fonts` + `fc-cache`，不需要 root），
     比 Noto Sans 更接近 Segoe UI 的字形比例。
3. **卡片/按钮的圆角与内边距**：模板里 `.card { padding: 16px 18px }` 对设计稿 18/20；
   `.btn` 高度、`.instance-item` 的 61 高与 13 半径都要按施工图落。
4. **顶部栏**：设计稿是「主题触发器（97.5×34）+ 日夜开关（57×30 胶囊）+ 分隔线 + 信息按钮」，
   GTK 侧把日夜做成带文字的按钮，形状不同。
5. **日志卡内部**：设计稿表头 45 高、行 27 高、时间列 + 级别 chip + 正文；GTK 侧行高与列宽不同。
6. **背景**：设计稿 body 有渐变 + `.scene` 装饰；GTK 用 `backgrounds/*.png`（已由同一条流水线生成），
   但要确认窗口层的 `background-size: cover` 与设计稿的裁切一致。

## 5. 门禁

`diff-shots.py` 已经能给出可比较的数字，后续把它接成 gate：
`tools/pixel-gate.py`（待写）逐主题跑「参考图 vs 实拍图」，MAE 超过阈值即失败，
并把最差区块打出来。阈值先定：MAE ≤ 3.0、超 16 像素 ≤ 3%。当前 8.68 / 13.09% 起步。
