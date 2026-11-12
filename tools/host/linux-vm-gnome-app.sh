#!/bin/bash
# Install our latest Linux manager deb and launch it inside the GNOME (Wayland) session,
# then take a portal screenshot so we can inspect HiDPI rendering.
set -u
DEB=${1:-/tmp/dsh-manager.deb}

echo "=== 安装 ==="
sudo -n dpkg -i "$DEB" 2>&1 | tail -3
dpkg-query -W -f='installed=%{Version}\n' dsh-manager 2>/dev/null

# 取图形会话的环境（Wayland）
pid=$(pgrep -f 'gnome-shell --mode' | head -1)
[ -z "${pid:-}" ] && { echo "no gnome-shell"; exit 1; }
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|WAYLAND_DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|XDG_SESSION_TYPE|XDG_CURRENT_DESKTOP)
      export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$pid/environ")
echo "env: WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-} DISPLAY=${DISPLAY:-} TYPE=${XDG_SESSION_TYPE:-}"

echo "=== 启动管理器 ==="
pkill -f '/usr/bin/dsh-manager' 2>/dev/null || true
sleep 1
setsid nohup /usr/bin/dsh-manager >/tmp/dshmgr-gnome.log 2>&1 &
sleep 10

echo "=== 窗口进程 ==="
pgrep -af 'dsh-manager|manager/gui' | head -3 || echo '(no process)'
tail -5 /tmp/dshmgr-gnome.log 2>/dev/null || true

echo "=== 截图 ==="
rm -f /home/twinblade/图片/Screenshot.png
gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Screenshot.Screenshot "" "{}" >/dev/null 2>&1
sleep 5
ls -l /home/twinblade/图片/Screenshot.png 2>/dev/null || echo '(no shot)'
