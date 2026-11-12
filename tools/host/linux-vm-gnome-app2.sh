#!/bin/bash
set -u
echo "=== gnome-shell ==="
pgrep -af gnome-shell | head -3 || echo none
echo "=== sessions ==="
for s in $(loginctl list-sessions --no-legend | awk '{print $1}'); do
  echo "session $s: $(loginctl show-session "$s" -p Type -p Desktop -p Active 2>/dev/null | tr '\n' ' ')"
done

pid=$(pgrep -f 'gnome-shell' | head -1)
if [ -z "${pid:-}" ]; then
  echo "=== 没有 gnome-shell，重启 sddm 登录 GNOME ==="
  sudo -n systemctl restart sddm
  sleep 22
  pid=$(pgrep -f 'gnome-shell' | head -1)
fi
echo "gnome-shell pid=${pid:-none}"
[ -z "${pid:-}" ] && exit 1

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
pgrep -af 'dsh-manager' | head -3 || echo '(no process)'
tail -8 /tmp/dshmgr-gnome.log 2>/dev/null || true

echo "=== 截图 ==="
rm -f /home/twinblade/图片/Screenshot.png
gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Screenshot.Screenshot "" "{}" >/dev/null 2>&1
sleep 6
ls -l /home/twinblade/图片/Screenshot.png 2>/dev/null || echo '(no shot)'
