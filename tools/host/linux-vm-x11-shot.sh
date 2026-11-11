#!/bin/bash
# 在 Ubuntu(Wayland) 里以 X11 后端启动管理器，方便 xdotool/import 截图与点击
set -u

# 1) 偷一份 GUI 会话的环境变量
src=$(pgrep -f 'gnome-shell|plasmashell|kwin_wayland' | head -1)
[ -z "$src" ] && src=$(pgrep -f 'dsh-manager' | head -1)
echo "env source pid=${src:-none}"
if [ -n "${src:-}" ]; then
  while IFS='=' read -r k v; do
    case "$k" in
      DISPLAY|WAYLAND_DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|XDG_SESSION_TYPE|DBUS_SESSION_BUS_ADDRESS|XDG_CURRENT_DESKTOP|XDG_SESSION_ID)
        export "$k=$v" ;;
    esac
  done < <(tr '\0' '\n' < "/proc/$src/environ")
fi
echo "DISPLAY=${DISPLAY:-} XAUTHORITY=${XAUTHORITY:-} DESKTOP=${XDG_CURRENT_DESKTOP:-} TYPE=${XDG_SESSION_TYPE:-}"

# 2) 停掉现有的管理器（Wayland 原生窗口，xdotool 看不见）
pkill -f '/usr/bin/dsh-manager' 2>/dev/null
sleep 2

# 3) 以 X11 后端重新拉起
export GDK_BACKEND=x11
setsid nohup /usr/bin/dsh-manager >/tmp/dshmgr-x11.log 2>&1 &
sleep 6

# 4) 找窗口 + 截图
echo "=== 窗口 ==="
ids=$(xdotool search --name "管理器" 2>/dev/null)
if [ -z "$ids" ]; then
  ids=$(xdotool search --class dsh-manager 2>/dev/null)
fi
if [ -z "$ids" ]; then
  echo "没找到窗口，列出全部可见窗口："
  xdotool search --onlyvisible --name "." 2>/dev/null | head -12 | while read -r id; do
    echo "  id=$id [$(xdotool getwindowname "$id" 2>/dev/null)]"
  done
  echo "--- 进程 ---"
  pgrep -a -f dsh-manager | head -3
  echo "--- 启动日志 ---"
  tail -12 /tmp/dshmgr-x11.log 2>/dev/null
  exit 0
fi

id=$(echo "$ids" | head -1)
echo "using window id=$id name=[$(xdotool getwindowname "$id" 2>/dev/null)]"
xdotool windowactivate "$id" 2>/dev/null || true
sleep 1
import -window "$id" /tmp/vm-shot.png 2>&1 | tail -2
ls -l /tmp/vm-shot.png 2>/dev/null || echo "shot failed"
