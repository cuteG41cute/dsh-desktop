# dsh-manager 3.2.0

本地语音从「一个专用服务」升级为「可切换的推理后端」，并接入通用引擎 audio.cpp。

## 新增：推理后端选择

「本地语音」页多了一行「推理后端」：

| 后端 | 说明 |
| --- | --- |
| **audio.cpp（推荐）** | 通用多模型引擎（143 个模型族）。管理器按需下载官方发行包（约 30–70 MB）与 GGUF 模型，自动生成 `server.json` 并托管进程；对外仍是 OpenAI 兼容接口 |
| codec.cpp（旧） | 原来的 Qwen3-TTS 专用服务，保留兼容 |

## 新增：模型库（audio.cpp）

| 模型 | 体积 | 特点 |
| --- | --- | --- |
| **Kokoro-82M** | 181 MB | 极小、接近实时、54 个内置音色（含中文 `zf_xiaobei`） |
| **Qwen3-TTS 0.6B** | 1.9 GB | 可克隆音色（参考音频） |

模型来自 ModelScope 的 `audio-cpp/audio.cpp-gguf`，按需下载；运行时从 audio.cpp 官方 Release 下载（优先国内镜像）。

## 实测

| 平台 | 动作 | 结果 |
| --- | --- | --- |
| Ubuntu 26.04（CPU） | Kokoro 合成中文 | 5.53 秒音频 / 3.5 秒完成（≈1.6× 实时） |
| Ubuntu 26.04（CPU） | Qwen3-TTS 0.6B（CLI） | 3.84 秒音频 / 9 秒（≈0.43× 实时） |
| Windows 11（CPU） | Kokoro 合成中文 | 4.4 秒音频 / 15.1 秒（首次含模型加载） |
| 两平台 | OpenAI 接口 | `GET /v1/models`、`POST /v1/audio/speech`、`GET /v1/audio/voices` 全部通 |

## 说明

- audio.cpp 与 codec.cpp 的 GGUF **不通用**（架构不同），切换后端时各自用各自的模型；
- 朗读插件不需要改：它只认 OpenAI 兼容地址，端口随后端变化（audio.cpp 用 8092，codec.cpp 用 8098），界面里「朗读接入」会同步显示；
- 旧后端与旧模型下载（models-v1 release）保持可用。
