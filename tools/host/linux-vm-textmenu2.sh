#!/bin/bash
# 选默认工作区 → 点输入框 → 打字 → 选中 → 右键，验证 text-menu
set -u
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

id=$(xdotool search --name "^DeepSeek Harness$" 2>/dev/null | head -1)
echo "session window=$id"
xdotool windowactivate "$id"; sleep 2
eval "$(xdotool getwindowgeometry --shell "$id")"

# 1) 侧栏「默认工作区」
xdotool mousemove $((X + 85)) $((Y + 300)); sleep 0.4; xdotool click 1; sleep 1.2
import -window "$id" /tmp/shot-step1.png

# 2) 输入框
xdotool mousemove $((X + 760)) $((Y + 380)); sleep 0.4; xdotool click 1; sleep 0.8
xdotool type --delay 60 "hello world"; sleep 1.0
import -window "$id" /tmp/shot-step2.png

# 3) 全选 + 右键
xdotool key --clearmodifiers ctrl+a; sleep 0.4
xdotool mousemove $((X + 700)) $((Y + 375)); sleep 0.3
xdotool click 3; sleep 1.2
import -window "$id" /tmp/shot-textmenu.png
echo "step1=$(ls -l /tmp/shot-step1.png 2>/dev/null | awk '{print $5}') step2=$(ls -l /tmp/shot-step2.png 2>/dev/null | awk '{print $5}') menu=$(ls -l /tmp/shot-textmenu.png 2>/dev/null | awk '{print $5}')"
xdotool key Escape
