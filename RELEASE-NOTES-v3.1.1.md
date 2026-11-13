# dsh-manager 3.1.1

Linux 版现在**自带语音服务程序**，装完只差模型。

## Linux：deb 里带上 `tts-server`

`dsh-manager_3.1.1_all.deb` 内置了用 codec.cpp 源码在 Linux 上编译的 `tts-server`（3.7 MB，安装到 `/usr/lib/dsh-manager/tts/tts-server`）。

- 管理器启动语音服务时会自动找：用户目录 `run/tts-server` → 包内的 `/usr/lib/dsh-manager/tts/tts-server`；
- 因此 Linux 用户不再需要自己编译，只剩**模型**要放：`~/.local/share/dsh-manager/services/tts/models/`（`qwen3-tts*.gguf` + `codec*.gguf`）；
- 页面会直接把该路径显示出来。

编译与运行环境：Ubuntu 26.04、gcc 15、glibc 2.43（更老的发行版（如 22.04）可能需要自行重编，或后续提供静态链接版）。

## 实测（Ubuntu 26.04 虚拟机）

| 步骤 | 结果 |
| --- | --- |
| 安装 deb 3.1.1 | `/usr/lib/dsh-manager/tts/tts-server` 就位，`--help` 正常 |
| 放模型后启动服务 | 启动成功，端口 8098，状态「运行中」，占用 1858 MB |
| 克隆音色（参考音频经 ffmpeg 转 24k 单声道） | 成功，列表出现 `linux-ref` |
| 合成一句中文 | 5.20 秒音频，用时 36.3 秒（纯 CPU） |
| 语速 1.2× | 249644 → 208422 字节，正常 |

## Windows

功能无变化，版本号跟进到 3.1.1（统一发版）。

## 仍然要你自己准备的东西

- 模型两个 GGUF（约 1.8 GB）。下一步计划是在管理器里加「下载模型」按钮，从发布源按需拉取并校验。
