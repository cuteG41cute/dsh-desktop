# 本机 ↔ 虚拟机 剪切板桥

Windows 和 Ubuntu 虚拟机之间**双向**同步文本剪切板，不用再手动来回粘。
纯脚本、走现有 SSH 通道，不改虚机里的桌面会话（不需要 Hyper-V 增强会话 / xrdp）。

## 装（一次性）

```powershell
powershell -ExecutionPolicy Bypass -File tools\clip\clip-bridge.ps1 -Deploy    # 把虚拟机半边推上去（顺带装 wl-clipboard）
powershell -ExecutionPolicy Bypass -File tools\clip\clip-bridge.ps1 -Install   # 开机自启 + 现在启动
```

装完之后在两边**任意一边** Ctrl+C / Ctrl+V 就行。

## 日常

| 命令 | 作用 |
| --- | --- |
| `clip-bridge.ps1 -Status` | 是否在跑 + 日志末尾 |
| `clip-bridge.ps1 -Start` / `-Stop` | 手动开关 |
| `clip-bridge.ps1 -Install` / `-Uninstall` | 开机自启的安装 / 卸载 |
| `clip-bridge.ps1 -Deploy` | 虚拟机重装或脚本更新后重新推送 |

日志：`%LOCALAPPDATA%\dsh-clip\bridge.log`
自启快捷方式：`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DSH-clipboard-bridge.lnk`

## 它是怎么做的

两条常驻 ssh 通道，各自带守护线程，断了自动重连（虚拟机在重启也不会崩）：

```
Windows 剪切板  ──host-bridge.py──▶ ssh ──▶ vm-apply.py ──▶ Klipper (DBus)   （本机 → 虚拟机）
Windows 剪切板  ◀──host-bridge.py── ssh ◀── vm-watch.py ◀── Klipper (DBus)   （虚拟机 → 本机）
```

- 本机侧用 `ctypes` 直接调 Win32 剪切板（`GetClipboardSequenceNumber` 判变化，
  不轮询文本内容），没有第三方依赖。
- 虚拟机侧走 Plasma 自带的剪贴板服务 **Klipper**（`org.kde.klipper` 的
  `getClipboardContents` / `setClipboardContents` + `clipboardHistoryUpdated` 信号）：
  一个常驻进程、**零 Wayland 客户端**，只在真的变化时读一次。
  非 Plasma 桌面时退回 `wl-paste --watch` / `wl-copy`（同样是事件驱动）。
- **防回声**：两边都按文本的 sha1 去重，只同步"和上次同步过的版本不同"的内容，
  所以不会 A→B 之后再弹回 B→A。
- **只同步文本**：剪切板里是图片/文件时整条跳过（不会把本机的文本顶掉）。
- 单条上限 4MB；超大文本跳过并写日志。

### 踩过的坑：不要轮询 Wayland 剪切板

第一版虚拟机侧是每 0.35 秒跑一次 `wl-paste --no-newline`。结果：**虚拟机里所有弹出菜单
（桌面右键、应用菜单）都变成"闪一下就消失"** —— 用户实测确认：把桥停掉，右键立刻恢复正常；
重新起桥，菜单又开始被顶掉。

原因：这种轮询每隔几百毫秒就在 KWin 里新建一个 Wayland 客户端、并向合成器请求剪贴板数据，
反复打断弹出的 grab。改成 Klipper DBus 之后，虚拟机侧不再创建任何 Wayland 客户端，
菜单恢复正常。**所以这里的设计原则是：虚拟机侧绝不轮询、绝不反复起 wl-* 进程。**


## 已知边界

- 虚拟机**重启后**：脚本在 `~/.local/share/dsh-clip/` 里，会自动重连；
  如果虚拟机是重装的，先跑一次 `-Deploy`。
- 服务器上没装 `wl-clipboard` 的，`-Deploy` 会尝试 `sudo -n apt-get install`
  （无密码 sudo 才行，否则手动装一次）。
- 图片/文件剪切板暂不同步。
- 虚拟机那边要能 `ssh` 免密登录（本机已经配好，`vm.ps1` 用的是同一套）。

## 自检

```powershell
python tools\clip\selftest.py
```

它自己起一份桥，双向各推一条中文/换行/20KB 文本并逐字比对，最后打印桥日志。
