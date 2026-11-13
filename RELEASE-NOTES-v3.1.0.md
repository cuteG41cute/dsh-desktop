# dsh-manager 3.1.0

**一次发布，两个平台**：Windows 管理器（`DshManager.exe`）+ Linux 管理器（`dsh-manager_3.1.0_all.deb`）。

## 新增：本地语音（Qwen3-TTS）

管理器自带「本地语音」页，把原本的网页管理页整个搬了进来：

- 服务状态 / 端口 / 模型文件 / 占用空间一目了然；
- 一个按钮切换 **启动 / 停止**（不再并排放两个）；
- 参考音色列表：每行 **试听 / 改名 / 删除**，音色数量实时更新；
- **新建音色**：填名字 → 选参考音频（WAV/MP3/M4A/FLAC）→ 自动转 24k 单声道 PCM16 → 上传克隆；
- 朗读接入：接口地址一键复制、音色下拉、语速 0.8/1.0/1.2/1.5、试听文本、「合成并播放」（变速用 ffmpeg atempo 在本机完成）；
- 服务端同步补齐 `PATCH /v1/audio/voices/<id>`（改名）与 `DELETE`（删音色，连 `.json`/`.gguf` 一起清）。

放置位置（Linux）：

```
~/.local/share/dsh-manager/services/tts/
  run/tts-server        # 编译好的服务程序（需自行提供）
  models/*.gguf         # qwen3-tts*.gguf + codec*.gguf
```

Windows 沿用 `%LOCALAPPDATA%\dsh-manager\services\tts`。

## 新增：顶栏插件芯片收进「插件」抽屉

会话窗口变窄时，顶栏那一排插件芯片（时间戳 / 网络 / 朗读 / 记忆库 / 备份 …）收成一枚 **`插件 N`**：

- 只收「插件芯片」本身；工作区下拉、`⋯`、右侧边栏这些产品控件不动、不藏、不挪；
- 点开药丸，芯片本体竖排浮出，点哪个弹的还是它自己的原生面板（开关 / 关闭都在）；
- 收起状态稳定，不会每秒来回闪；Esc 或再点一次收起；
- Windows 与 Linux 桌面窗口加载的是**同一份** `chips-drawer.js`。

## 其他

- Linux 管理器新增 `本地语音` 页与 `--headless` 之外的页面直达：`DSH_MANAGER_START_PAGE=tts`；
- 两处小修：面包屑在非概览页不再被刷新覆盖；音频上传一律先转码，避免「不是 PCM16 WAV」报错；
- 版本号统一：Windows `3.1.0`、Linux 包 `3.1.0`。
