#!/bin/bash
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
echo "=== user systemd 环境 ==="
systemctl --user show-environment 2>/dev/null | grep -E 'WAYLAND_DISPLAY|DISPLAY|DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR|XDG_SESSION_TYPE' || true

WAYLAND_DISPLAY=$(systemctl --user show-environment 2>/dev/null | sed -n 's/^WAYLAND_DISPLAY=//p')
WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0}
export WAYLAND_DISPLAY

echo "=== 重启管理器（带 Wayland 环境）==="
pkill -f '/usr/bin/dsh-manager' 2>/dev/null || true
sleep 1
setsid nohup /usr/bin/dsh-manager >/tmp/dshmgr-gnome.log 2>&1 &
sleep 10
pgrep -af 'dsh-manager' | head -2 || echo '(no process)'
tail -6 /tmp/dshmgr-gnome.log 2>/dev/null || true

echo "=== 截图 ==="
rm -f /home/twinblade/图片/Screenshot.png
gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Screenshot.Screenshot "" "{}" >/dev/null 2>&1
sleep 6
ls -l /home/twinblade/图片/Screenshot.png 2>/dev/null || echo '(no shot)'
