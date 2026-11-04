# 会话窗口增强 · 版本适配表

内置会话窗口（WebView2）里那套「预览/文件增强」是按 **dsh 版本**分流的，不是一刀切。

## 判定规则

```
取实例的 dsh 版本（正则去掉 -rc.x / -alpha.x 之类的预发布后缀）
  0.1.x            → 旧 UI（legacy）
  >= 0.2.0         → 新 UI（modern）
  取不到 / 解析失败 → 按新 UI 处理，并在 web.log 写一行标记
```

对应源码：`DshWebWindow.Preview.cs` 里的 `IsLegacyUi()` 与 `AttachPreviewTools()`。

## 两套 UI 的差异（为什么必须分流）

| | 旧 UI（0.1.x） | 新 UI（0.2.x 起） |
| --- | --- | --- |
| 文件树行 | 没有 `data-files-*` 属性 | `<li data-files-entry="file\|directory" data-files-path="/abs">` |
| 预览容器 | `[data-image-preview]` / `.dsh-pv-vp` | `.rIfSMq_scrollport` + `.rIfSMq_surface` |
| 缩放 | 产品没有 | **官方有**：`Ctrl + 滚轮`，改 `--document-zoom`（宽度），并带右上角工具栏 |
| 右键菜单 | 产品没有 | **官方有**：保存到… / 复制文件路径 / 资源管理器显示 / 复制图片 |

## 注入什么

| 版本 | 注入 | 提供的能力 |
| --- | --- | --- |
| **0.1.x** | `preview-tools.js`（旧桌面版那份原样） | 滚轮缩放（光标为锚）、拖动平移、右键保存/复制/显示、文件行与交付卡拖出\n |
| **>= 0.2.0** | `image-pan.js` + `file-dragout.js`（新写） | 只补官方没有的两半：**放大后拖动平移**、**文件/目录拖出到系统**；缩放与右键完全交给官方 |
| 未知 | 同 `>= 0.2.0` | 同上；`web.log` 会记录 `preview profile: dsh=? -> modern` |

两个新脚本都是**自检式**的：命中不到自己的选择器就什么都不做（`__dshPan` / `__dshDragOut` 只挂一次），所以即使某个版本 DOM 又改，也只是“不生效”，不会像早期那样把整页滚动锁死。

## 开关

「窗口功能」窗口里的两个开关只对 **>= 0.2.0** 生效（0.1.x 那套是整包脚本）：

- `WebPan` → 是否注入 `image-pan.js`
- `WebDragOut` → 是否注入 `file-dragout.js`

存在 `%APPDATA%\dsh-manager\settings.json`。

## 已知边界

- 新 UI 的**交付卡**（会话里那些文件卡片）暂未支持拖出——卡片 DOM 上不一定带绝对路径；
- 旧 UI 的脚本会接管滚轮，因此 **0.1.x 实例**里普通滚轮的行为由它决定（当年就是按那套 DOM 调的）；
- 产品再改 DOM 时，`web.log` 里的 `dom probe` 与 `preview profile` 两行能第一时间看出来。
