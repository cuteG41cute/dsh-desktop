#!/bin/bash
# 在会话窗口里验证「输入框右键菜单」（text-menu.js）
set -u
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

id=$(xdotool search --name "^DeepSeek Harness$" 2>/dev/null | head -1)
[ -z "$id" ] && id=$(xdotool search --name "DeepSeek Harness" 2>/dev/null | grep -v 18874376 | head -1)
echo "session window=$id"
[ -z "${id:-}" ] && { echo "没有会话窗口"; exit 1; }

xdotool windowactivate "$id"; sleep 2
eval "$(xdotool getwindowgeometry --shell "$id")"
echo "geo=${WIDTH}x${HEIGHT} at ${X},${Y}"

# 点输入框（居中偏下的 composer），输入文字
xdotool mousemove $((X + 700)) $((Y + 390)); sleep 0.4; xdotool click 1; sleep 0.5
xdotool type --delay 40 "hello world"; sleep 0.8
# 选中一段（Ctrl+A 会选中页面/输入框内容，这里用 Home+Shift+End）
xdotool key --clearmodifiers Home; sleep 0.2
xdotool key --clearmodifiers shift+End; sleep 0.3
# 右键
xdotool mousemove $((X + 700)) $((Y + 380)); sleep 0.3
xdotool click 3; sleep 1.2
import -window "$id" /tmp/shot-textmenu.png
echo "shot=$(ls -l /tmp/shot-textmenu.png 2>/dev/null | awk '{print $5}')"
# 关掉菜单
xdotool key Escape; sleep 0.3
