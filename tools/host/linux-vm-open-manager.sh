#!/bin/bash
# Launch dsh-manager inside the running GNOME Wayland session.
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
export XDG_SESSION_TYPE=wayland
export XDG_CURRENT_DESKTOP=ubuntu:GNOME

echo "=== 先清掉旧进程 ==="
pkill -f '/usr/bin/dsh-manager' 2>/dev/null || true
sleep 2

echo "=== 启动 ==="
setsid nohup /usr/bin/dsh-manager >/tmp/dshmgr.log 2>&1 &
sleep 12

echo "=== 进程 ==="
pgrep -af 'dsh-manager' | head -3 || echo '(没启动)'
echo "=== 日志 ==="
tail -12 /tmp/dshmgr.log 2>/dev/null || echo '(无日志)'
echo "=== 崩溃日志 ==="
tail -6 /home/twinblade/.config/dsh-manager/crash.log 2>/dev/null || echo '(无)'

echo "=== 截图 ==="
rm -f /home/twinblade/图片/Screenshot.png
gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Screenshot.Screenshot "" "{}" >/dev/null 2>&1
sleep 6
ls -l /home/twinblade/图片/Screenshot.png 2>/dev/null || echo '(no shot)'
