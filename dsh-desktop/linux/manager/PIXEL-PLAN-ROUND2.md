# 第二轮（2026-10-31 16:2x）

| 指标 | 第一轮末 | 现在 |
| --- | --- | --- |
| 14 套主题平均 MAE | 8.86 | **7.71** |
| frost/day 概览 | 5.86 | **5.54** |
| crystal-night 概览 | 31.67 | **19.88** |
| crystal-day 概览 | — | **5.81** |
| 门禁 | 可跑 | 可跑（PASS，28 组预算已更新） |

## 这轮定位到的三类问题

1. **主题专属皮肤没实现**。设计稿里 crystal 主题的卡片不是纯色，而是
   `linear-gradient(135deg, rgba(255,255,255,.62), var(--card))` 加
   `inset 2px 2px 0 rgba(255,255,255,.35)` 高光。GTK 侧一直是纯色，所以 crystal 相差最远。
   现在由 `build-gtk-theme.py` 按主题名注入（`THEME_SKINS`），色值仍走令牌替换。
2. **GTK 同时给 background-color 和 gradient 会叠两层**（设计稿用的是 `background` 简写，
   渐变直接盖掉底色）。半透明色被算两次 → 卡片明显偏亮。皮肤里先把
   `background-color: transparent` 清掉。
3. **背景图的取景错了**。`.scene` 是 `position:fixed`，设计稿里铺满 1440×900，
   窗口内容只看到 (24,24)-(1416,876) 那一块。原来是按 1392×852 视口渲染的，
   光斑/水晶的绝对位置偏了 48px。现在按 1440×900 渲染再裁窗格。

## 两件"已验证没问题"的事（省得下一轮再猜）

- **配色**：`tools/design-tokens.mjs` 把设计稿 29 个 CSS 变量 × 14 组合全导出，
  `tools/host/token-diff.py` 与管理器 `themes.json` 逐项比 —— **266 个色值全部一致**。
- **字号**：`tools/host/vm-gtk-spec.py` 现在用 Pango 上下文报真实字号，
  与设计稿逐类对比：eyebrow 8 / card-label 11 / instance-name 11.5 / instance-sub 10 /
  log-title 12 / side-link 11.5 / breadcrumb 11 —— 全部相等。

## 新增诊断工具

| 文件 | 作用 |
| --- | --- |
| `tools/design-tokens.mjs` + `tools/host/token-diff.py` | 配色逐项比对（不看像素） |
| `tools/host/align-shift.py` | 估整体位移（当前各组合 dx=0, dy=0~-3px） |
| `tools/host/diff-blur.py` | 模糊后再比，拆分"文字抗锯齿"与"结构误差" |
| `tools/host/patch-color.py` | 指定矩形比较平均色，快速定位"这块为什么不一样" |
| `tools/probe-element.mjs` | 问浏览器某坐标最上面是谁画的、什么背景 |

`diff-blur.py` 的结论：frost/flat/crystal-day 的高频误差只占 15~20%，
说明剩下 80% 仍是结构/配色，不是字体栅格化 —— 还有得压。

## 下一轮的靶子

1. crystal-night（19.88）与 crystal-night-settings（20.71）是唯一的大离群点，
   其余 26 组集中在 4.5~9。先把这两个压下去，平均能掉到 6 以下。
2. 顶栏日夜开关改成设计稿的"太阳+月亮胶囊+滑块"。
3. 日志卡空态（`还没有日志`）与行高列宽。
4. 把 `pixel-gate.py` 和 `token-diff.py` 一起接进发布检查。
