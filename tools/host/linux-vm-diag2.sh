#!/bin/bash
set -u
PREFIX=/home/twinblade/.local/opt/deepseek-harness-2
echo "=== share/web 是否已铺进去 ==="
ls -l "$PREFIX/share/web" 2>/dev/null | head -8 || echo "(没有 share/web)"
echo "=== share/dsh-desktop.py 版本特征 ==="
grep -c "load_web_scripts" "$PREFIX/share/dsh-desktop.py" 2>/dev/null || echo "(旧版：没有 load_web_scripts)"
echo "=== desktop.log 尾部 ==="
tail -25 "$PREFIX/logs/desktop.log" 2>/dev/null
echo "=== 窗口进程 ==="
pgrep -a -f "share/dsh-desktop" | head -3
echo "=== 所有窗口 ==="
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;; esac
done < <(tr '\0' '\n' < "/proc/$src/environ")
xdotool search --onlyvisible --name "" 2>/dev/null | head -12 | while read -r w; do
  echo "  id=$w name=[$(xdotool getwindowname "$w" 2>/dev/null)] class=$(xprop -id "$w" WM_CLASS 2>/dev/null | sed 's/.*= //')"
done
