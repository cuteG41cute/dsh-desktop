# dsh-manager 3.2.8

修掉音色列表「每秒闪一次 / 选别的音色又跳回 narrator」的问题。

## 原因

`UpdateTtsCard` 每秒跑一次刷新，`RefreshAudioVoicesAsync` 每次都：

1. 清空音色列表、重建所有行；
2. 清空「音色」下拉再重新填充；
3. 重建后把选中项设回第一个（narrator）。

所以既闪、又选不住。

## 改法

- **音色集合签名**（模型 + 全部音色名）没变就**不重建**，只同步选中项和「默认」标签；
- 选中项存进 `AppSettings.AudioVoice`，重建时按它恢复，不再回落第一个；
- 「默认」标签改成直接切换可见性，不重新创建控件。

## 平台

- Windows：`AppSettings.AudioVoice`（settings.json）
- Linux：`services/audiocpp/voice.json`，下拉的 changed 回调持久化

## 实测

设置里预置 `AudioVoice=af_bella` 后启动，界面保持 `af_bella`，不再跳回 narrator；连续两次截图（间隔 4 秒）内容一致，无闪烁。
