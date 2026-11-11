#!/bin/bash
# 在 Ubuntu(KDE Wayland) 里把管理器以 X11 后端拉起，并用 xdotool + import 截图
set -u

src=$(pgrep -x plasmashell | head -1)
[ -z "${src:-}" ] && src=$(pgrep -f dsh-manager | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|WAYLAND_DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|XDG_SESSION_TYPE|XDG_CURRENT_DESKTOP)
      export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

echo "env: DISPLAY=${DISPLAY:-} XAUTHORITY=${XAUTHORITY:-} DESKTOP=${XDG_CURRENT_DESKTOP:-}"

pkill -f '/usr/bin/dsh-manager' 2>/dev/null || true
sleep 2

export GDK_BACKEND=x11
setsid nohup /usr/bin/dsh-manager >/tmp/dshmgr-x11.log 2>&1 &
sleep 8

echo "=== 进程 ==="
pgrep -a -f dsh-manager | head -3

echo "=== 窗口 ==="
ids=$( { xdotool search --name "管理器" 2>/dev/null; xdotool search --class "dsh-manager" 2>/dev/null; } | sort -u )
if [ -z "$ids" ]; then
  echo "(没找到窗口) 可见窗口列表："
  xdotool search --onlyvisible --name "" 2>/dev/null | head -10 | while read -r i; do
    echo "  id=$i name=[$(xdotool getwindowname "$i" 2>/dev/null)]"
  done
  echo "=== 日志 ==="
  tail -15 /tmp/dshmgr-x11.log 2>/dev/null
  exit 0
fi

for id in $ids; do
  echo "  id=$id name=[$(xdotool getwindowname "$id" 2>/dev/null)] geo=$(xdotool getwindowgeometry "$id" 2>/dev/null | tr '\n' ' ')"
done
id=$(echo "$ids" | head -1)
xdotool windowactivate "$id" 2>/dev/null || true
sleep 1
import -window "$id" /tmp/vm-shot.png 2>&1 | tail -2
ls -l /tmp/vm-shot.png 2>/dev/null || echo "shot failed"
