#!/bin/bash
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
OUT=/tmp/gnome-shot.png
rm -f "$OUT"
echo "=== 尝试 GNOME Shell 截图接口 ==="
gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell/Screenshot \
  --method org.gnome.Shell.Screenshot.Screenshot false false "$OUT" 2>&1 | head -3
ls -l "$OUT" 2>/dev/null || echo '(shell screenshot failed)'

echo "=== 环境信息 ==="
loginctl show-session 215 -p Desktop -p Type -p Active 2>/dev/null || true
echo "gnome-shell: $(pgrep -a gnome-shell | head -1)"
echo "分辨率: $(wayland-info 2>/dev/null | grep -m1 -i 'current' || echo '?')"
