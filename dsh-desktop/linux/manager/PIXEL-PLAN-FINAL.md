# 像素级复刻：收尾报告（2026-10-31）

## 结论

| 维度 | 判据 | 现状 | 结论 |
| --- | --- | --- | --- |
| 配色 | `token-diff.py --strict`（29 变量 × 14 组合 = 266 个色值） | **266/266 完全一致** | 与设计稿一致 |
| 几何 | `geometry-gate.py`（27 元素，±2px） | 侧栏/顶栏/内容区/卡片/快捷按钮/图标/头像/日志卡全部 ≤2px | 与设计稿一致 |
| 像素 | `pixel-gate.py`（28 组合 MAE） | 平均 **5.55**，中位 5.20，最好 3.62，13/28 ≤ 5.0 | 见"引擎下限" |

三道门禁一条命令跑完：`powershell -ExecutionPolicy Bypass -File tools\host\pixel-check.ps1`
（`-Update` 刷新预算；现返回 `RESULT: PASS`）

## 目标里"可重复流水线"的证据

从零重跑一遍（重新生成 28 张参考图、重建 14 份主题、重拍 28 张 GTK 图、跑门禁），
逐组合数字与上一轮**完全一致**（例如 frost-day-dashboard 3.807、flat-day 3.615），
说明流水线是确定性的，不是靠手工调出来的。

## 达到"引擎下限"的部分（不可能再压）

1. **字体栅格化**：设计稿由 Chromium 渲染（subpixel 定位 + 自己的 hinting），
   GTK 用 Pango + FreeType。同一字号下字形边缘不同，`diff-blur.py` 实测：
   模糊 1.5px 后误差只降 15~20%，即大部分残差是**文字边缘**，不是布局。
   设计稿字体栈还是 Windows 专有的（Segoe UI / Microsoft YaHei UI）。
2. **crystal 主题的 `backdrop-filter: blur(22px)`**：GTK3 没有这个能力。
   设计稿的卡片是"半透明玻璃叠在被模糊的背景上"，GTK 只能叠在清晰背景上。
   这就是 `crystal-night` 系列一直高于其他组合的原因，属于能力边界。
   已在该主题上按设计稿补了 `linear-gradient(135deg, rgba(255,255,255,.62), card)`
   + `inset` 高光（`build-gtk-theme.py` 的 `THEME_SKINS`），把差距从 31.67 压到 11.04。

## 这轮修的两个真 bug（都值得记档）

1. **GTK 的 CSS `margin` 与 `set_margin_*()` 会相加**，不是覆盖。
   日志卡因此上边距变成 40px（设计稿 20），整卡低 20px —— 这就是此前
   "表头比卡片顶低 21px"的真身。规则：**外边距只写一处**。
2. **GTK 的 `min-height` 是内容盒**，设计稿的 `height` 是 border-box。
   卡片 205 直接写进 min-height 会变成 241（多 36 = padding 18×2），
   正确写法是 `205 − padding − border = 167`。
3. 顶栏 `min-height` 写了两处（65/66），后者生效 → 顶栏 67 而非 66，整页下移 1px。

## 三个可直接复用的工具

| 工具 | 用途 |
| --- | --- |
| `tools/design-shot.mjs` / `design-spec.mjs` / `design-tokens.mjs` | 设计稿 → 参考图 / 施工图 / 色值表 |
| `tools/extract-icons.mjs` → `dsh_manager/icons/*.svg` | 设计稿 25 个图标变成运行时资源（按主题色着色） |
| `tools/host/vm-gtk-shot.py` / `vm-gtk-spec.py` | GTK 离屏出图（任意尺寸）/ 控件几何导出 |
| `tools/host/pixel-check.ps1` | 三道门禁串联 |

## 真机验收

在虚拟机上直接跑源码版（`PYTHONPATH=~/dsh-dev python3 -m ...`）并截真机桌面：
`vm-shots/dev-final2.png` —— 1280×720 屏幕下窗口完整、卡片/快捷功能区/日志卡/顶栏控件
（主题触发器 + 日夜胶囊 + 分隔线 + 信息按钮）都在位。
为此把内容区横向策略从 NEVER 改成 AUTOMATIC：布局按设计稿 1392 宽钉死，
窗口更窄时给横向滚动条，而不是把右半边裁掉（原来会裁）。

## 怎么继续

- 改完 UI：`vm-gtk-shot.py` 出图 → 拉回 `vm-shots/gtk/` → `pixel-check.ps1` 看有没有回归。
- 想再压 pixel MAE：只能针对**非文字元素**（阴影、圆角、半透明叠色）微调；
  文字相关误差属于引擎下限。
- crystal 主题若要真复刻，需要在 GTK 里自绘"取背景区域 → 模糊 → 合成卡片"，
  代价高且窗口一改尺寸就失效，暂不做。
