#!/bin/bash
# 用实例自带的 node 重启桌面窗口（启动器需要 PATH 里有 node），然后截图确认。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade
XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
[ -n "${XA:-}" ] && export XAUTHORITY="$XA"
unset DISPLAY GDK_BACKEND
export PATH="$HOME/Program/deepseek-harness-1/node/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

kscreen-doctor --dpms on >/dev/null 2>&1
pkill -f 'dsh-desktop.py http://127.0.0.1:3080' 2>/dev/null
pkill -f 'share/dsh-desktop$' 2>/dev/null
sleep 2
: > /tmp/dsh-desktop-live.log
setsid nohup bash "$HOME/Program/deepseek-harness-1/share/dsh-desktop" >>/tmp/dsh-desktop-live.log 2>&1 &
sleep 14
echo '== 进程'
pgrep -af 'dsh-desktop' | grep -v pgrep | head -5
echo '== 日志'
grep -v -e DeprecationWarning -e '^  ' /tmp/dsh-desktop-live.log | head -20
echo '== 截图'
python3 /tmp/vm-shot.py /tmp/after-restart.png 2>&1 | tail -1
