# dsh-manager 3.1.2

缺模型时，本地语音页会出现 **「下载模型」** 按钮 + 进度条，点一下就自动下载（支持断点续传）。

## 下载源：为什么默认不是 ModelScope

我先试了 ModelScope 上现成的 Qwen3-TTS GGUF（`qwqpotato/qwen3-tts-gguf`），用我们的 `tts-server` 实测**不兼容**：

```
load failed: no audio-LM recipe for this codec GGUF (architecture qwen3-tts-tokenizer)
llama_model_load: error loading model: unknown model architecture: 'qwen3-tts'
```

那套 GGUF 是给 audio.cpp 用的（tokenizer/backbone 架构不同），codec.cpp 需要的是「codec + backbone」这一对。

所以默认下载源改成了**我们自己发布的 codec.cpp 兼容模型**（`models-v1` release），并按顺序尝试：

1. 环境变量 `DSH_TTS_MODEL_BASE`（可以指向你自己的 ModelScope 仓库）
2. 国内加速镜像 `gh-proxy.com`
3. GitHub 原站

实测（虚拟机到各源）：

| 源 | 速度 |
| --- | --- |
| GitHub 直连 | ~226 KB/s |
| `gh-proxy.com` 镜像 | ~1.8 MB/s |
| ModelScope 官方文件 | ~7 MB/s |

如果你有 ModelScope 账号，可以把这两个 GGUF 传上去，然后设 `DSH_TTS_MODEL_BASE=https://modelscope.cn/models/<你的仓库>/resolve/master/`，就能吃到 ModelScope 的速度。

## 实现细节

- 逐文件串行下载，先落 `.part`，完成后改名；中断重试会带 `Range` 续传；
- 已存在且体积 ≥ 预期 95% 的文件直接跳过（第二次点击秒完成）；
- 进度条按字节比例更新，旁边显示当前文件名与百分比；
- Windows / Linux 行为一致。

## 实测

| 项 | 结果 |
| --- | --- |
| 进度回调 | 10%→100% 连续上报（单文件 325 MB，49.3 秒，327 次回调） |
| 完成后改名 | `.part` → 正式文件名 ✓ |
| 重复点击 | 0.00 秒直接返回「模型下载完成」✓ |
| 缺模型的界面 | 「下载模型」按钮 + 进度条正常出现（见截图） |

## 版本

Windows `DshManager.exe` 与 Linux `dsh-manager_3.1.2_all.deb` 一起发布。
