# dsh-manager 3.2.6

四项一起收尾：音色闭环、Kokoro 音色列表、OmniVoice 提醒、下载可取消。

## 1. 参考音色接到 audio.cpp

「新建音色」现在会：

- 让你填**音色名字** + **参考文本**（这段音频说了什么，克隆模型需要）；
- 音频统一转 24k 单声道，存成 `audiocpp/voices/<名字>.wav`；
- 参考文本写进 `voices/prompt_text`（`名字|文本` 一行）；
- 服务在跑就自动重启，新音色立刻出现在「音色」下拉里。

实测（Linux）：`add_voice('ref2', ...)` → 目录里出现 `ref2.wav`，`prompt_text` 内容为 `ref2|你好，这是参考音频的文本。`；服务端 `/v1/audio/voices` 返回 `['ref2']`。

## 2. Kokoro 的 54 个音色

audio.cpp 不通过接口暴露 Kokoro 的 preset，管理器内置官方列表（53 个 id：`af_heart`、`zf_xiaobei`、`zm_yunjian`…），后端是 Kokoro 时直接出现在「音色」下拉里。实测 `voice=zf_xiaobei` 合成 4.28 秒音频成功。

## 3. OmniVoice 提醒

选中 OmniVoice 前弹确认框：「纯 CPU 一次合成可能 10 分钟以上，期间服务会一直忙」。避免误点后卡住。Linux 端同样是模态确认框。

## 4. 下载可取消

- Windows：下载中的行出现「取消」按钮，点了立刻杀掉 curl、保留 `.part`（下次可续）；
- Linux：同样的「取消」按钮，置位取消事件，下载线程在下一个 chunk 抛出取消，返回「已取消」。
