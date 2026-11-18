# dsh-manager 3.4.2

参考音色卡片底部加了**试听生成状态条**。

## 行为

点任意音色的「试听」后，音色列表下方出现一条浅紫底状态条：

```
[不确定进度条]  1.2 秒 · 生成中…
```

- 每 100ms 刷新一次耗时；
- 生成完成后变成 `2.7 秒 · 生成完成`，进度条隐藏，2.5 秒后整条淡出；
- 失败时直接收起状态条并弹失败原因。

## 平台

- Windows：`TtsVoiceStatusBox`（Border + ProgressBar + TextBlock，DispatcherTimer 计时）
- Linux：`tts_voice_status`（Gtk.ProgressBar.pulse + GLib.timeout_add 计时）

## 顺带修

`bump-version.ps1` 里新加的中文报错字符串被 PowerShell 5.1 按 ANSI 读坏了（脚本无 BOM 时中文会乱码导致语法错误），现在改成 ASCII 报错并给文件加了 BOM。
