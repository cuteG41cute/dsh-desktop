# 远程接管虚拟机（SSH 一条通道，能改代码 / 跑 GUI / 截图 / 调试）

验证时间：2026-10-31 15:28–15:33，主机 `172.22.144.1` → VM `twinblade@172.22.148.197`。
以下每条都真跑过，产出的图在 `vm-shots/`。

## 0. 先记住这条：别把 shell 片段塞进 ssh 参数

Windows PowerShell 5.1 往原生程序传参时会吃掉引号（实测 `python3 -c "print(1)"` 到了 VM 上
变成 `python3 -c print(1)`，`$`、`"`、`(` 全坏）。所以全部走「本地写文件 → 上传 → 执行」：

```powershell
powershell -ExecutionPolicy Bypass -File tools\host\vm.ps1 -Script tools\host\xxx.sh
powershell -ExecutionPolicy Bypass -File tools\host\vm.ps1 -Script tools\host\xxx.py -Args '/tmp/out.png'
powershell -ExecutionPolicy Bypass -File tools\host\vm.ps1 -Script .\x.sh -Fetch /tmp/a.png -FetchDir vm-shots
```

`vm.ps1` 会按后缀选解释器（`.sh`→bash，`.py`→python3），把远端 stderr 并进 stdout，
跑完删远端临时文件，`-Fetch` 再把指定文件拉回本地。

## 1. 会话环境（所有 GUI 操作的前提）

VM 是 KDE Plasma 6 / Wayland，SSH 进来是个没有显示上下文的 shell。以下变量要齐：

```bash
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export DISPLAY=:1                       # Xwayland
export WAYLAND_DISPLAY=wayland-0
export XAUTHORITY=$(ls /run/user/1000/xauth_* | head -1)
```

`/proc/<kwin>/environ` 读不了（权限），但 `/proc/<plasmashell>/environ` 能读，上面这些就是从它抄出来的。

## 2. 截图（VM 上没装任何截图工具也能拍）

`spectacle` / `grim` / `import` / `ffmpeg` / `scrot` **全部没装**，但系统自带
`xdg-desktop-portal-kde` + `gdbus` + `python3-gi` + `PIL`，所以：

`tools/host/vm-shot.py`（上传到 `/tmp/vm-shot.py`）三级回退：

| 后端 | 做法 | 实测 |
| --- | --- | --- |
| `portal` | `org.freedesktop.portal.Screenshot`，`interactive=false`，订阅 `Request.Response` 拿 uri | ✅ 1280×720 全屏，775 KB，见 `vm-shots/vm-1528-portal.png` |
| `kwin` | `org.kde.KWin.ScreenShot2.CaptureActiveScreen/CaptureArea`，传一个临时文件 fd，KWin 写 BGRA | 代码就绪（`area:x,y,w,h`），主路径已够用 |
| `xwd` | Xwayland root 窗口 | ❌ `BadMatch (X_GetImage)`，Xwayland root 取不出来 |

要点：portal 的 `Screenshot` 调用只返回一个 request 对象路径，**必须**先订阅
`org.freedesktop.portal.Request.Response`（信号里的 `uri` 才是文件），否则永远等不到图。
另外用「临时文件」而不是 pipe 接 KWin 的像素：pipe 只有 64 KB，1280×720×4 = 3.7 MB，
写完之前读端不读就是死锁。

## 3. 窗口管理（列出 / 聚焦 / 关窗）

`tools/host/vm-kwin-script.sh` + 一个 JS 文件，走 KWin 脚本接口：

```bash
gdbus call --session --dest org.kde.KWin --object-path /Scripting \
  --method org.kde.kwin.Scripting.loadScript /tmp/x.js      # 返回脚本号
gdbus call --session --dest org.kde.KWin --object-path /Scripting/Script<号> \
  --method org.kde.kwin.Script.run
```

JS 里 `workspace.windowList()` 拿所有窗口（有 `caption` / `resourceClass` / `closeWindow()`，
`workspace.activeWindow = w` 可聚焦）。实测脚本输出进 journal：

```
journalctl --user -n 200 --no-pager | grep 'js:'
js: window: plasmashell/plasmashell |
js: window: dsh-manager/python3.14 | DeepSeek Harness 管理器 1.3.3
js: window: / | 调试控制台
```

踩到的坑：我手滑调了 `org.kde.KWin.showDebugConsole`，调试控制台窗口**盖住**了管理器，
而且它的 `resourceClass` 是空串（不是 `kwin`），第一版按 class 过滤没关掉 —— 改按标题
「调试控制台」匹配后关掉了。见 `vm-shots/manager-wl.png`（被盖住）→ `vm-shots/manager-clean.png`（干净）。

## 4. 跑 GUI 程序

```bash
setsid nohup /usr/bin/dsh-manager >> /tmp/log 2>&1 < /dev/null &
```

`setsid` + `nohup` + 重定向 stdin 三件套必须齐，否则 SSH 断开时子进程跟着死。
GL 在 VM 里是坏的（`ZINK: failed to choose pdev`），给 `LIBGL_ALWAYS_SOFTWARE=1` 兜底，
GTK3 走软件渲染没问题。

实测画面：`vm-shots/manager-clean.png` —— 实例列表（harness-1 运行中绿点、harness-2 已停止）、
概览、快捷控制、常用功能、`运行环境正常 Python 3.14.4 · GTK 3.24.52` 全都在。

## 5. 改代码 → 跑起来 → 看效果（不开 root）

已装的代码在 `/usr/lib/dsh-manager/`（要 sudo 才能改），所以开发副本走 `~/dsh-dev`：

```powershell
tar -czf $env:TEMP\manager-dev.tgz -C dsh-desktop\linux\manager --exclude=__pycache__ dsh_manager
scp -P 22 $env:TEMP\manager-dev.tgz twinblade@172.22.148.197:/tmp/manager-dev.tgz
powershell -File tools\host\vm.ps1 -Script tools\host\vm-run-dev-manager.sh -Args /tmp/dev.png
```

`vm-run-dev-manager.sh` 会解包到 `~/dsh-dev`、`PYTHONPATH=$HOME/dsh-dev python3 -c
'from dsh_manager.cli import main; main()'` 启动、等 10 秒、截图、打印日志尾巴。
实测：5.3 MB 源码树上传 → 启动 → `vm-shots/dev-manager.png`（263 KB）。

## 6. 主题逐套核验（终于能自动出图了）

`tools/host/vm-gui-shot.py`：不点按钮、不靠合成器，直接把真窗口渲染出来存 PNG ——
导入 `dsh_manager.gui`、建 `ManagerWindow`、`apply_theme(theme, mode, persist=False)`、
`_show_page(name)`，然后 `Gdk.pixbuf_get_from_window` 取窗口像素（X11 后端，XGetImage）。

```powershell
powershell -File tools\host\vm.ps1 -Script tools\host\vm-gui-shot.py -Args '/tmp/gui'
```

结果 **28/28 全通过**：7 套主题（frost/liquid/crystal/flat/alpine/dawn/sea）× 日/夜 × 2 页
（dashboard/settings），每张都 `theme_ok=True`、`last_theme_error()` 为空。汇总图：
`vm-shots/sheet-dashboard.png`，明细在 `vm-shots/gui/`。

这条路比截全屏更适合像素比对：没有壁纸、没有任务栏、没有标题栏，尺寸稳定（实测 1220×614）。

踩到的坑：
- `gi.require_foreign("cairo")` 报 `No module named 'gi._gi_cairo'` —— VM 缺 `python3-gi-cairo`，
  `win.draw(cairo.Context)` 走不通，改用 X11 `Gdk.pixbuf_get_from_window`（无需该包）。
- `from gi.repository import Gdk` 必须先 `gi.require_version("Gdk", "3.0")`，否则它抢到 Gdk 4.0
  然后跟 GTK3 冲突报 `Requiring namespace 'Gdk' version '3.0', but '4.0' is already loaded`。

## 7. 现在还做不到的（以及怎么补上）

| 能力 | 现状 | 补法 |
| --- | --- | --- |
| 点按钮 / 敲键盘 | ❌ 没有 `xdotool`/`ydotool`/`wtype`；Wayland 合成器也没有注入接口 | 跑 `sudo bash ~/share/fix-vm-sudo.sh`（已加 `xdotool`）：X11 后端下的窗口能点；或装 `ydotool`（要 uinput） |
| 改 `/usr/lib/dsh-manager`、apt 装包、systemctl | ❌ sudo 要密码，SSH 里给不了 | 跑一次 `sudo bash ~/share/enable-vm-nopasswd-sudo.sh`，之后 `sudo -n` 直通（撤销：删 `/etc/sudoers.d/90-dsh-agent`） |
| 现在能替代"点击"的办法 | ✅ 程序内驱动：直接调用 `apply_theme` / `_show_page` / `resp.start()` 等方法，等价于点按钮触发的代码路径 | 见 §6 |

## 8. 文件清单

| 文件 | 作用 |
| --- | --- |
| `tools/host/vm.ps1` | 上传并执行本地 `.sh`/`.py`，`-Fetch` 拉回产物 |
| `tools/host/vm-shot.py` | 全屏截图（portal → KWin → xwd） |
| `tools/host/vm-kwin-script.sh` | 跑 KWin JS（列窗口/聚焦/关窗） |
| `tools/host/kwin-fix-focus.js` | 关调试控制台 + 聚焦管理器 |
| `tools/host/vm-run-dev-manager.sh` | 把 `~/dsh-dev` 的开发副本跑起来并截图 |
| `tools/host/vm-gui-shot.py` | 逐主题/逐页离屏渲染窗口 PNG（可做像素比对） |
| `tools/host/pull-vm-backup.ps1` | 把 VM 里只在 VM 上的东西拉回主机留档 |
| `tools/host/list-hyperv-checkpoints.ps1` | 管理员权限下列/导出 Hyper-V 检查点 |
