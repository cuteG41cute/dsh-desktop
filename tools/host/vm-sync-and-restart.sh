#!/bin/bash
# 把新版启动器 + 窗口脚本同步进两个实例和 deb 安装目录，然后重启桌面窗口。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade
XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
[ -n "${XA:-}" ] && export XAUTHORITY="$XA"
unset DISPLAY GDK_BACKEND

echo '== 同步文件'
for d in /usr/lib/dsh-manager/share "$HOME/Program/deepseek-harness-1/share" "$HOME/.local/opt/deepseek-harness-2/share"; do
  [ -d "$d" ] || continue
  cp -f /tmp/new-dsh-desktop "$d/dsh-desktop" 2>/dev/null && chmod +x "$d/dsh-desktop"
  cp -f /tmp/new-dsh-desktop.py "$d/dsh-desktop.py" 2>/dev/null
  echo "$d: launcher=$(stat -c%s "$d/dsh-desktop" 2>/dev/null) shell=$(stat -c%s "$d/dsh-desktop.py" 2>/dev/null) popup=$(grep -c '__dshPopupClosed' "$d/dsh-desktop.py" 2>/dev/null)"
done

kscreen-doctor --dpms on >/dev/null 2>&1
pkill -f 'dsh-desktop.py http://127.0.0.1:3080' 2>/dev/null
pkill -f 'share/dsh-desktop$' 2>/dev/null
sleep 2
export PATH="$HOME/Program/deepseek-harness-1/node/bin:/usr/local/bin:/usr/bin:/bin"
: > /tmp/dsh-desktop-live.log
setsid nohup bash "$HOME/Program/deepseek-harness-1/share/dsh-desktop" >>/tmp/dsh-desktop-live.log 2>&1 &
sleep 14
echo '== 进程'
pgrep -af 'dsh-desktop' | grep -v pgrep | head -5
echo '== 日志'
grep -v -e DeprecationWarning -e '^  ' /tmp/dsh-desktop-live.log | head -20
echo '== 截图'
python3 /tmp/vm-shot.py /tmp/after-restart.png 2>&1 | tail -1
