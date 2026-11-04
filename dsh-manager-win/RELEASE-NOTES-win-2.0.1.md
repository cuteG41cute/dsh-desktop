# dsh-manager Windows 2.0.1

2.0.0 之后的一处修复。

## 修复

**最小化 / 最大化 再还原之后，主窗口四角的方形灰角又出现了。**

原因：窗口圆角是靠 `SetWindowRgn` 给窗口设一个圆角区域实现的，而**最小化 → 还原**、**最大化 → 还原** 这两种状态切换会让系统把窗口区域清掉，方角就重新露出来（启动、切主题之所以正常，是因为那两条路径本来就会重设一次）。

处理：

- 监听 `StateChanged`：最小化/还原/最大化都补裁一次，并且补**两次**（立刻一次 + 120ms 后一次，防止系统在我们之后才重置）；
- 自绘的「最大化 / 还原」（按工作区手动铺，不走 `WindowState.Maximized`）两条分支结束后各补一次；
- 主题切换后也补一次；
- 半径统一读主题资源 `AppRadiusValue`，不会和内容圆角脱节。

实测日志：

```
17:46:04.814 state -> Minimized
17:46:04.815 window region 2616x1680 r=52 ok=1
17:46:04.951 window region 2616x1680 r=52 ok=1
17:46:07.067 state -> Normal
17:46:07.069 window region 2616x1680 r=52 ok=1
17:46:07.200 window region 2616x1680 r=52 ok=1
```

## 安装

下载 `DshManager.exe` 覆盖到 `%LOCALAPPDATA%\Programs\DSH Manager\` 即可（或用 `install-win.ps1`）。
