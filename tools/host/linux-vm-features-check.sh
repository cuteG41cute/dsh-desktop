#!/bin/bash
set -u
sudo -n dpkg -i /tmp/dsh-manager.deb >/dev/null 2>&1 || true
echo "版本: $(dpkg-query -W -f='${Version}' dsh-manager)"
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")
export GDK_BACKEND=x11
python3 /tmp/vm-features-check.py 2>&1 | tail -n 14
