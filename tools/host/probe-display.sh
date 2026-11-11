#!/bin/bash
set -u
echo "=== 候选 GUI 进程 ==="
for name in plasmashell kwin_wayland kwin_x11 gnome-shell dsh-manager; do
  pid=$(pgrep -x "$name" | head -1 || true)
  [ -z "$pid" ] && pid=$(pgrep -f "$name" | head -1 || true)
  if [ -n "${pid:-}" ]; then
    echo "--- $name pid=$pid"
    tr '\0' '\n' < "/proc/$pid/environ" | grep -E '^(DISPLAY|XAUTHORITY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|XDG_SESSION_TYPE)=' || echo "  (无相关变量)"
  fi
done
echo "=== loginctl 会话 ==="
loginctl list-sessions --no-legend 2>/dev/null | head -4
for s in $(loginctl list-sessions --no-legend 2>/dev/null | awk '{print $1}'); do
  echo "session $s: $(loginctl show-session "$s" -p Type -p Display -p Seat -p Active 2>/dev/null | tr '\n' ' ')"
done
echo "=== X sockets ==="
ls -l /tmp/.X11-unix 2>/dev/null
echo "=== Xauthority 文件 ==="
ls -l /run/user/1000/xauth_* "$HOME/.Xauthority" 2>/dev/null
