#!/bin/bash
set -u
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

id=$(xdotool search --name "管理器" 2>/dev/null | head -1)
echo "window=$id"
xdotool windowactivate "$id"; sleep 1
eval "$(xdotool getwindowgeometry --shell "$id")"
# 侧栏刷新按钮：窗口内相对坐标 (190,107)
xdotool mousemove $((X + 190)) $((Y + 107)); sleep 0.3
xdotool click 1
sleep 0.15
import -window "$id" /tmp/vm-shot-refresh1.png 2>&1 | tail -1
sleep 0.9
import -window "$id" /tmp/vm-shot-refresh2.png 2>&1 | tail -1
ls -l /tmp/vm-shot-refresh1.png /tmp/vm-shot-refresh2.png 2>/dev/null | awk '{print $5, $9}'
