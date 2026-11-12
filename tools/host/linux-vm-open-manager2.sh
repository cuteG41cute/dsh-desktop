#!/bin/bash
# Launch dsh-manager strictly on Wayland (no X fallback) inside the GNOME session.
set -u
unset DISPLAY
unset XAUTHORITY
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export GDK_BACKEND=wayland
export XDG_SESSION_TYPE=wayland
export XDG_CURRENT_DESKTOP=ubuntu:GNOME

pkill -f '/usr/bin/dsh-manager' 2>/dev/null || true
sleep 2
: > /tmp/dshmgr.log
setsid nohup /usr/bin/dsh-manager >/tmp/dshmgr.log 2>&1 &
sleep 12

echo "=== 进程 ==="
pgrep -af 'dsh-manager' | head -3 || echo '(没启动)'
echo "=== 日志 ==="
cat /tmp/dshmgr.log 2>/dev/null | tail -15 || echo '(无)'

echo "=== 截图 ==="
rm -f /home/twinblade/图片/Screenshot.png
gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Screenshot.Screenshot "" "{}" >/dev/null 2>&1
sleep 6
ls -l /home/twinblade/图片/Screenshot.png 2>/dev/null || echo '(no shot)'
