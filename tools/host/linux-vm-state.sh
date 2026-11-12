#!/bin/bash
set -u
echo "=== gnome-shell 进程 ==="
pgrep -af 'gnome-shell' | head -3 || echo '(none)'
echo "=== 会话状态 ==="
for s in $(loginctl list-sessions --no-legend | awk '{print $1}'); do
  echo "session $s: $(loginctl show-session "$s" -p Type -p Desktop -p Active -p State -p Seat 2>/dev/null | tr '\n' ' ')"
done
echo "=== 显示 scale ==="
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
gdbus call --session --dest org.gnome.Mutter.DisplayConfig \
  --object-path /org/gnome/Mutter/DisplayConfig \
  --method org.gnome.Mutter.DisplayConfig.GetCurrentState 2>/dev/null \
  | tr ',' '\n' | grep -m3 "1920x1080" 
