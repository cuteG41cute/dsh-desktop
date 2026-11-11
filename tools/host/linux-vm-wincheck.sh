#!/bin/bash
set -u
echo "=== 窗口进程 ==="
pgrep -a -f "dsh-desktop" | head -5
echo "=== 管理器日志文件 ==="
ls -lt ~/.config/dsh-manager/ 2>/dev/null | head -10
echo "=== manager.log 尾部 ==="
tail -25 ~/.config/dsh-manager/manager.log 2>/dev/null
echo "=== 所有可见窗口（含类名）==="
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")
for w in $(xdotool search --onlyvisible --name "" 2>/dev/null | head -12); do
  echo "  id=$w name=[$(xdotool getwindowname "$w" 2>/dev/null)] class=[$(xprop -id "$w" WM_CLASS 2>/dev/null | head -1)]"
done
