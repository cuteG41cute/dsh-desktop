# dsh-manager 3.4.1

下拉框底色改成和输入框一样的白底。

## 原因

自定义的 `ComboBox` 模板里，`ToggleButton` 没有把 `Background` 传下去，WPF 就用了系统默认的按钮灰底。

## 改法

1. `ToggleButton` 上补 `Background="{TemplateBinding Background}"`、`BorderBrush` 同理；
2. 下拉框底色从半透明 `Card` 改成实色 `CardSolid`（和「朗读接入」里输入框的底色一致）。

现在三个下拉（推理后端 / 音色 / 语速）都是白底 + inner-border + 右侧 chevron，跟输入框同一套观感。
