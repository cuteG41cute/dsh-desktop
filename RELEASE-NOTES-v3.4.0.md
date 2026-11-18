# dsh-manager 3.4.0

按设计稿 `ui-redesign/voice-model.html` 落地下拉框与试听播放态。

## 1. 下拉框（TtsCombo）

从设计稿 `voice-model.css` 抄的数值：

| 属性 | 值 |
| --- | --- |
| 高度 | 32 |
| 圆角 | 8 |
| 边框 | 1px inner-border |
| 背景 | card |
| 字号 | 8.5–9 |
| 右侧箭头 | chevron 图标，距右 10 |
| 悬停 | 边框转 accent-soft |
| 聚焦 | 外圈 accent 光环（opacity .35） |
| 下拉面板 | 圆角 9、卡片底色、投影、内边距 4、最大高 260 滚动 |
| 选项 | 圆角 6，悬停 Hover 底色，选中 AccentSoft |

应用对象：推理后端、音色、语速三个下拉。

## 2. 试听播放态（voice-row.playing）

点「试听」后：

- 整行底色变 `AccentSoft`、边框变 `Accent`（35% 观感）；
- 麦克风图标淡化到 0.25；
- 头像左下出现**三根跳动的竖条**（高 4/8/6，0.65s 往复，依次延迟 0/150/300ms）；
- 按钮文字变「停止」；
- 再点一次 = 停止播放并复位；播放结束自动复位。

## 3. 说明

- 数值（圆角、间距、字号、动画时长）都来自 `voice-model.css`；
- 交互逻辑参考设计稿的 `.playing` 类与 `voice-bar` keyframes；
- Linux 端下拉框由 GTK CSS 控制，样式本来就独立，播放态动画待补。
