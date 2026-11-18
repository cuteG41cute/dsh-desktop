# dsh-manager 3.3.4

切到 codec.cpp 后端时，「模型库」不再显示 audio.cpp 的模型列表。

## 原因

「模型库」那块是 audio.cpp 后端的模型清单（Kokoro、OmniVoice、IndexTTS2.5…），codec.cpp 根本用不了这些 GGUF —— codec.cpp 只认 Qwen3-TTS 的 codec + backbone **一对** GGUF（也就是它自己的 `qwen3-tts-0.6b-q8_0.gguf` + `codec-q8_0.gguf`）。

之前切到 codec.cpp 时列表照旧显示 + 单选按钮还能点，属于「给了不存在的选择」。

## 现在

| 后端 | 模型区域显示 |
| --- | --- |
| audio.cpp | 8 个模型的单选列表（保持原样） |
| codec.cpp | 一句说明：「codec.cpp 只支持 Qwen3-TTS（codec + backbone 一对 GGUF）」+ 当前这对文件名/缺失提示 |

两平台一致（Windows `UpdateTtsCardCodec`、Linux `_refresh_codec`）。

另外：codec.cpp 的音色仍然走它自己的 `/v1/audio/voices`，与 audio.cpp 的 voice_dir 互不影响。
