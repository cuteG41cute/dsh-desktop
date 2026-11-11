#!/bin/bash
set -u
pid=$(pgrep -f "dsh-desktop.py" | head -1)
echo "window pid=$pid"
echo "=== stderr/stdout 目标 ==="
ls -l /proc/$pid/fd/1 /proc/$pid/fd/2 2>/dev/null
echo "=== 该进程打开的日志文件 ==="
ls -l /proc/$pid/fd 2>/dev/null | grep -E "log|debug" | head -5
echo "=== 注入日志（从 stderr 目标里找）==="
tgt=$(readlink /proc/$pid/fd/2 2>/dev/null)
if [ -n "${tgt:-}" ] && [ -f "$tgt" ]; then tail -20 "$tgt"; fi
echo "=== dsh-desktop 相关文件 ==="
ls -lt /tmp/*.log 2>/dev/null | head -5
tail -20 /tmp/dsh-desktop*.log 2>/dev/null
echo "=== 窗口列表（含类名/几何）==="
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;; esac
done < <(tr '\0' '\n' < "/proc/$src/environ")
for w in $(xdotool search --name "." 2>/dev/null | head -20); do
  cls=$(xprop -id "$w" WM_CLASS 2>/dev/null | sed 's/.*= //')
  echo "  id=$w name=[$(xdotool getwindowname "$w" 2>/dev/null)] class=$cls geo=$(xdotool getwindowgeometry "$w" 2>/dev/null | grep Geometry)"
done
