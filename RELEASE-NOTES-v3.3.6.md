# dsh-manager 3.3.6

新建音色「选了文件却什么都没发生」——原因是当前后端是 **codec.cpp**，而 codec 的服务没启动。

## 原因

「新建音色」按后端走两条路：

| 后端 | 添加音色的方式 |
| --- | --- |
| audio.cpp | 直接把 wav + 参考文本写进 `audiocpp/voices`（**不需要服务在跑**） |
| codec.cpp | 调用 codec 服务的 `/v1/audio/voices` 上传（**要求 8098 在运行**） |

你当时切到了 codec.cpp（截图里端口 8098、模型 qwen3-tts + codec），服务是「已停止」，所以上传请求发不出去——而且旧代码只更新了一个不显眼的状态文字，看起来就是「啥也没发生」。

## 改法

codec 后端下点「新建音色」时，先检查服务：

- 没运行 → 直接提示：**「codec.cpp 服务没在运行：先点『启动服务』，或把『推理后端』切到 audio.cpp」**，不再白跑一趟；
- 运行中 → 正常上传。

Linux 端同步加了同样的检查。

## 另外

audio.cpp 后端的新建音色不依赖服务，已经用调试 CLI 验证过：

```
--tts-addvoice testvoice demo.wav  ->  ok=True  msg=音色已创建：testvoice
```

写入位置：`%LOCALAPPDATA%\dsh-manager\services\audiocpp\voices\{名字}.wav` + `prompt_text`。
