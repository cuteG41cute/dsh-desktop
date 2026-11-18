# dsh-manager 3.3.5

修「点新建音色报错」。

## 原因

`PromptText`（管理器的通用输入对话框）里写死了：

```csharp
Background = (Brush)FindResource("WindowBackground")
```

但 `WindowBackground` 这个资源在任何主题里都**不存在**（主题里的背景键叫 `Bg` / `App`）。资源找不到 → 抛异常 → 新建音色的按钮事件直接崩掉，对话框根本没弹出来。

之前没暴露是因为「新建音色」走的是另一条旧路径；3.2.6 之后 audio.cpp 分支开始调用 `PromptText` 才踩到。

## 改法

- 新增 `SafeBrush(key, fallback)`：用 `TryFindResource` 逐个尝试，最后兜底 `Transparent`；
- `PromptText` / `Confirm` 的背景改用 `SafeBrush("WindowBackground", "CardSolid")`；
- 再包一层 try/catch：对话框打不开时弹提示并写 `crash.log`（`prompt-text: ...`），不再让按钮事件崩掉。
