#!/bin/bash
# 装包 → 重启管理器（X11）→ 截顶栏 → 点「窗口功能」→ 截对话框
set -u
deb="${1:-/tmp/dsh-manager.deb}"
sudo -n dpkg -i "$deb" >/dev/null 2>&1 || true
echo "版本: $(dpkg-query -W -f='${Version}' dsh-manager)"

src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

pkill -f '/usr/bin/dsh-manager' 2>/dev/null || true
sleep 2
export GDK_BACKEND=x11
setsid nohup /usr/bin/dsh-manager >/tmp/dshmgr-x11.log 2>&1 &
sleep 8

id=$(xdotool search --name "管理器" 2>/dev/null | head -1)
echo "window=$id"
[ -z "${id:-}" ] && { tail -20 /tmp/dshmgr-x11.log; exit 1; }
xdotool windowactivate "$id"; sleep 1
eval "$(xdotool getwindowgeometry --shell "$id")"
echo "geo=${WIDTH}x${HEIGHT}"

import -window "$id" /tmp/shot-top.png 2>&1 | tail -1
echo "top=$(ls -l /tmp/shot-top.png 2>/dev/null | awk '{print $5}')"

# 「窗口功能」按钮在顶栏右侧，打开窗口左侧：窗口内相对坐标约 (992,113)
xdotool mousemove $((X + 992)) $((Y + 113)); sleep 0.3
xdotool click 1
sleep 1.5
import -window root /tmp/shot-dialog.png 2>&1 | tail -1
echo "dialog=$(ls -l /tmp/shot-dialog.png 2>/dev/null | awk '{print $5}')"
echo '=== settings.json ==='
cat "$HOME/.config/dsh-manager/settings.json" 2>/dev/null
