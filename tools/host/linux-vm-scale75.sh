#!/bin/bash
# Try to shrink the UI below 100%: monitor scale 0.75 is not supported by GNOME,
# so use text-scaling-factor 0.75 as the practical alternative.
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

echo "=== 1) 尝试把显示器 scale 设成 0.75（预期被拒）==="
gdbus call --session --dest org.gnome.Mutter.DisplayConfig \
  --object-path /org/gnome/Mutter/DisplayConfig \
  --method org.gnome.Mutter.DisplayConfig.ApplyMonitorsConfig \
  1 2 "[(0, 0, 0.75, 0, true, [('Virtual-1', '1920x1080@60.000', {})])]" "{}" 2>&1 | head -2

echo "=== 2) 回读当前 scale ==="
gdbus call --session --dest org.gnome.Mutter.DisplayConfig \
  --object-path /org/gnome/Mutter/DisplayConfig \
  --method org.gnome.Mutter.DisplayConfig.GetCurrentState 2>/dev/null \
  | tr ',' '\n' | grep -m2 '1920x1080'

echo "=== 3) 改用文字缩放 0.75 ==="
gsettings set org.gnome.desktop.interface text-scaling-factor 0.75
gsettings get org.gnome.desktop.interface text-scaling-factor
gsettings get org.gnome.desktop.interface font-name
gsettings get org.gnome.desktop.interface document-font-name

echo "=== 4) 重新拉起管理器，让它按新缩放渲染 ==="
export WAYLAND_DISPLAY=wayland-0
export GDK_BACKEND=wayland
unset DISPLAY
pkill -f '/usr/bin/dsh-manager' 2>/dev/null || true
sleep 2
setsid nohup /usr/bin/dsh-manager >/tmp/dshmgr.log 2>&1 &
sleep 12
pgrep -af 'dsh-manager' | head -2 || echo '(not running)'

echo "=== 5) 截图 ==="
rm -f /home/twinblade/图片/Screenshot.png
gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Screenshot.Screenshot "" "{}" >/dev/null 2>&1
for i in $(seq 1 12); do sleep 2; [ -f /home/twinblade/图片/Screenshot.png ] && { echo "shot ok"; break; }; done
ls -l /home/twinblade/图片/Screenshot.png 2>/dev/null || echo '(no shot)'
