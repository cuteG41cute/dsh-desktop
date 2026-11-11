#!/bin/bash
# 截图验证：滚到底部看「删除实例」卡 + 点刷新按钮
set -u
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;; esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

id=$(xdotool search --name "管理器" 2>/dev/null | head -1)
if [ -z "$id" ]; then echo "no window"; exit 1; fi
echo "window=$id"
xdotool windowactivate "$id" 2>/dev/null || true
sleep 1
eval "$(xdotool getwindowgeometry --shell "$id")"
echo "geo=${WIDTH}x${HEIGHT} at ${X},${Y}"

# 鼠标移到页面中部，向下滚 8 格
xdotool mousemove $((X + WIDTH / 2)) $((Y + HEIGHT / 2))
sleep 0.3
for _ in $(seq 1 8); do xdotool click 5; sleep 0.12; done
sleep 1
import -window "$id" /tmp/vm-shot-bottom.png 2>&1 | tail -1
echo "bottom shot: $(ls -l /tmp/vm-shot-bottom.png 2>/dev/null | awk '{print $5}') bytes"

# 点侧栏刷新按钮（窗口内相对坐标约 190,107）
xdotool mousemove $((X + 190)) $((Y + 107))
sleep 0.3
xdotool click 1
sleep 0.25
import -window "$id" /tmp/vm-shot-refresh.png 2>&1 | tail -1
echo "refresh shot: $(ls -l /tmp/vm-shot-refresh.png 2>/dev/null | awk '{print $5}') bytes"
