# PIXEL-PLAN 进度附录（2026-10-31 16:00，第一轮）

| 指标 | 动手前 | 现在 |
| --- | --- | --- |
| frost/day 概览 MAE | 8.68 | **5.86** |
| frost/day 像素差 >16 占比 | 13.09% | **4.94%** |
| 14 套主题平均 MAE | 22.68（夜间全崩） | **8.86** |
| 最好组合 | — | flat-day 概览 4.69 |
| 最差组合 | — | crystal-night 概览 31.67（配色待查） |

## 这轮改了什么（每条都对着 design/styles.css 的数字）

1. **去掉外壳 18px 外边距**：设计稿 `.app-shell` 就是窗口本身，留边距等于整体内缩。
2. **GTK 的 min-height 是内容盒**（设计稿 height 含 padding+border）：
   实例行 79→61、快捷按钮 110→82、主按钮 40→38、侧栏链接 42→40，全部按
   `height - padding - border` 重算。这是体量最大的一处系统性偏差。
3. **侧栏**：padding 26/16/18、brand 下边距 28、列表 3×61+2×5、新建实例 38 高、
   底部块 margin-top 24、运行环境卡 56 高。列表改用 `set_min_content_height` ——
   原来 ScrolledWindow 只分到 41px，3 个实例被裁成 1 个。
4. **卡片**：实例卡 663.73 / 控制卡 402.25（原来写死 310）、高度 205、内边距 18/20、
   网格间距 16；快捷功能 82 高、图标 34×34 居中、区块间距 21/11。
5. **顶栏**：主题触发器钉到 34 高并垂直居中；日夜开关 57×30。
6. **图标**：抽出设计稿 25 个 SVG 到 `dsh_manager/icons/`，运行时替换 `currentColor`
   再交给 GdkPixbuf 的 svg loader；新增 `_icon()/_recolor_icons()`，切主题自动重上色。
   快捷功能区、侧栏三个链接、日志标题、按钮图标都已换成设计稿图标。
7. **离屏截图修了个真问题**：`Gtk.OffscreenWindow` 没带 `dsh-window` class，
   拍不到窗口背景 → 夜间主题全变成"半透明卡片浮在灰底"（MAE 40+）。
   补上 class 后夜间 40.88 → 7.63。

## 新增工具

| 文件 | 作用 |
| --- | --- |
| `tools/extract-icons.mjs` | 设计稿 `<symbol>` → `dsh_manager/icons/*.svg` |
| `tools/design-spec.mjs` | 设计稿关键元素的几何/配色 → `spec-*.json` |
| `tools/host/vm-gtk-shot.py` | GTK 离屏出图（任意尺寸，含窗口背景） |
| `tools/host/vm-gtk-spec.py` | GTK 控件几何/字号 → JSON，和施工图逐项比 |
| `tools/host/pixel-gate.py` | 逐主题跑 MAE，超预算即失败（`design/pixel-budget.json`） |
| `tools/host/vm_fixture.py` | 与设计稿一致的假数据（实例/日志/PID/端口） |

## 下一步

1. **配色**：crystal/alpine 夜间偏差最大 —— 在浏览器里跑 `getComputedStyle` 把
   design 的 `--*` 变量全取出来，和 `themes.json` 逐项对比（比逐像素快得多）。
2. **字号**：Pango 行高与设计稿不完全一致，h1/正文略大，逐类对 `font-size`。
3. **顶栏日夜开关**：设计稿是"太阳+月亮胶囊+滑块"，GTK 现在还是文字按钮。
4. **日志卡**：压掉 `还没有日志` 空态；表头/行高/列宽再对。
5. 把平均 MAE 压到 ≤3，并把 `pixel-gate.py` 接进发布检查。
