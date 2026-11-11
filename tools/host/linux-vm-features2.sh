#!/bin/bash
# 只做验证：点「窗口功能」→ 截对话框 → 切一个开关 → 保存 → 看 settings.json
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

# 点「窗口功能」
xdotool mousemove $((X + 992)) $((Y + 113)); sleep 0.3; xdotool click 1
sleep 1.5

dlg=$(xdotool search --name "窗口功能" 2>/dev/null | head -1)
echo "dialog=$dlg"
if [ -n "${dlg:-}" ]; then
  eval "$(xdotool getwindowgeometry --shell "$dlg")"
  echo "dialog geo=${WIDTH}x${HEIGHT} at ${X},${Y}"
  import -window "$dlg" /tmp/shot-dialog.png
  echo "dialog shot=$(ls -l /tmp/shot-dialog.png 2>/dev/null | awk '{print $5}')"
else
  echo "没有找到对话框窗口；管理器可见窗口："
  xdotool search --onlyvisible --name "" 2>/dev/null | head -8 | while read -r w; do
    echo "  $w [$(xdotool getwindowname "$w" 2>/dev/null)]"
  done
fi
echo '===== settings.json ====='
cat "$HOME/.config/dsh-manager/settings.json" 2>/dev/null || echo '(不存在)'
