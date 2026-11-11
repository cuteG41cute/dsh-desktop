#!/bin/bash
set -u
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;; esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

id=$(xdotool search --name "管理器" 2>/dev/null | head -1)
echo "window=$id"
xdotool windowactivate "$id"; sleep 1
eval "$(xdotool getwindowgeometry --shell "$id")"
# 点一下页面中部拿焦点，再按 End / Page_Down
xdotool mousemove $((X + WIDTH / 2 + 100)) $((Y + HEIGHT / 2))
xdotool click 1
sleep 0.4
for _ in 1 2 3 4; do xdotool key --clearmodifiers Page_Down; sleep 0.25; done
xdotool key --clearmodifiers End
sleep 1
import -window "$id" /tmp/vm-shot-bottom.png 2>&1 | tail -1
echo "shot1=$(ls -l /tmp/vm-shot-bottom.png 2>/dev/null | awk '{print $5}')"

# 侧栏刷新按钮：窗口内相对坐标（190,107）
X0=$X; Y0=$Y
xdotool mousemove $((X0 + 190)) $((Y0 + 107)); sleep 0.3; xdotool click 1
sleep 0.2
import -window "$id" /tmp/vm-shot-refresh.png 2>&1 | tail -1
echo "shot2=$(ls -l /tmp/vm-shot-refresh.png 2>/dev/null | awk '{print $5}')"
