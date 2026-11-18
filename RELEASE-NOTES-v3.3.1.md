# dsh-manager 3.3.1

把 audio.cpp 运行时（含静态 eSpeak）直接打进安装包，英文 Kokoro 音色开箱可用。

## Windows

- `DshManager.exe` 内嵌 `audiocpp_server.exe`（37.5 MB）+ `espeak-ng-data.bin`（17.5 MB）；
- 首次启动释放到 `%LOCALAPPDATA%\dsh-manager\services\audiocpp\bin\`，写 `runtime.version = audiocpp-espeak-v1`；
- 之后升级只在版本标记变化时重新释放，不会每次覆盖；
- exe 从 66 MB 变成 **89 MB**（单文件压缩后）。

实测：删掉 bin 目录后启动管理器，运行时被正确释放，`af_heart` 合成 **129,644 字节 / 2.7 秒**。

## Linux

- deb 内置 `/usr/lib/dsh-manager/audio-cpp/{audiocpp_server, espeak-ng-data.bin}`；
- 管理器查找顺序：**用户目录**（下载的）→ **deb 自带**（带 eSpeak）；
- 启动时工作目录取可执行文件所在目录，保证 eSpeak 数据能被找到；
- deb 从 5 MB 变成 **31 MB**（xz 压缩后）。

实测（删掉用户目录运行时后）：`server=/usr/lib/.../audiocpp_server`，英文 `af_heart` **2.70 秒**、中文 `zf_xiaobei` **3.40 秒**。

## 运行时来源优先级（两平台一致）

1. deb / exe 内置的 espeak 版；
2. 用户目录里已下载的；
3. 在线下载（先试我们发布的 espeak 资产，再回退官方包）。
