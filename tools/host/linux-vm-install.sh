#!/bin/bash
# 装 /tmp/dsh-manager.deb 并重启管理器（X11 后端，方便截图）
set -u
deb="${1:-/tmp/dsh-manager.deb}"
echo "=== 安装 $deb ==="
sudo -n dpkg -i "$deb" 2>&1 | tail -6
sudo -n apt-get -f install -y 2>&1 | tail -3
echo "=== 版本 ==="
dpkg-query -W -f='${Version}\n' dsh-manager

src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|WAYLAND_DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|XDG_CURRENT_DESKTOP)
      export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

pkill -f '/usr/bin/dsh-manager' 2>/dev/null || true
sleep 2
export GDK_BACKEND=x11
setsid nohup /usr/bin/dsh-manager >/tmp/dshmgr-x11.log 2>&1 &
sleep 8

id=$(xdotool search --name "管理器" 2>/dev/null | head -1)
echo "window id=${id:-none}"
if [ -n "${id:-}" ]; then
  xdotool windowactivate "$id" 2>/dev/null || true
  sleep 1
  import -window "$id" /tmp/vm-shot.png 2>&1 | tail -1
  ls -l /tmp/vm-shot.png
else
  tail -12 /tmp/dshmgr-x11.log
fi
