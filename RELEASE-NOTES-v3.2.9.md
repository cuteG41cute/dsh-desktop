# dsh-manager 3.2.9

音色「试听」失败的两个原因都定位了，并做了兜底。

## 原因一：Kokoro 不支持「参考音色」

narrator 是我们上传的参考音频，属于克隆类模型的音色；Kokoro 只会用它内置的 preset。把 narrator 当 voice 传给 Kokoro，服务端会走 eSpeak 兜底然后报错。

## 原因二：英文 preset 需要 eSpeak-ng

运行时是官方 `cpu-portable` 包，**没有内置 eSpeak-ng**。所有英文音色（`af_*`、`am_*`、`bf_*`、`bm_*`、`ef_*`、`hf_*`、`jf_*`、`pf_*` 等）都会报：

```
Could not load eSpeak-ng; install the shared library or provide its path
```

中文音色（`zf_*`、`zm_*`）不依赖 eSpeak，实测正常（141 KB / 4.2 秒）。

## 兜底逻辑

点「试听」时如果失败且后端是 Kokoro：

1. 自动改用 `zf_xiaobei` 再合成一次，能出声就先让你听到；
2. 提示条写明原因：「「af_heart」需要 eSpeak-ng（当前运行时未内置），已用中文音色 zf_xiaobei 试听」。

这样至少不会出现「点了没反应也不知道为什么」。

## 我试过但没成功的修法

把 eSpeak-ng 的 `libespeak-ng.dll` + `espeak-ng-data` 放进 runtime 目录、并在 `server.json` 里配 `kokoro_tts.espeak_library_path` —— 服务端直接拒绝：

```
unknown Kokoro TTS session option: kokoro_tts.espeak_library_path
```

Kokoro 这个 family 不接受该 session option。要让英文音色真正可用，只能换 **编译时静态链接 eSpeak 的 audio.cpp 版本**（`-DAUDIOCPP_STATIC_ESPEAK=ON`），官方发行包没提供。

## 下一步建议

1. 在虚拟机上用 `-DAUDIOCPP_STATIC_ESPEAK=ON` 重新构建 Linux 版（可行，约 15 分钟），验证英文音色；
2. Windows 端需要 MSVC 工具链才能同样构建（这台机器目前只有 dotnet SDK），得先装 VS Build Tools；
3. 或者暂时把英文 preset 标注为「需要 eSpeak」，只展示中文 8 个音色。

你先在 3.2.9 里点一下 narrator 和 zf_xiaobei 的试听，确认兜底是否按预期出声。
