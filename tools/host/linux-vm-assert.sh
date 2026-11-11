#!/bin/bash
# Install the new deb on the VM, restart the session window with debug on,
# then assert the injected feature flags through the control socket.
set -u
PREFIX=/home/twinblade/.local/opt/deepseek-harness-2
PORT=3081

echo "=== install ==="
sudo -n dpkg -i /tmp/dsh-manager.deb 2>&1 | tail -2
echo -n "installed="; dpkg-query -W -f='${Version}\n' dsh-manager
echo -n "system_jsrun="; grep -c 'js-run begin' /usr/lib/dsh-manager/share/dsh-desktop.py 2>/dev/null || echo 0

src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")
export GDK_BACKEND=x11

echo "=== restart window ==="
pkill -f "share/dsh-desktop" 2>/dev/null || true
sleep 2
: > "$PREFIX/logs/desktop.log" 2>/dev/null || true
DSH_DESKTOP_DEBUG=1 dsh-manager --headless open --prefix "$PREFIX" 2>&1 | tail -2
sleep 12

echo "=== injected ==="
grep -a "injected" "$PREFIX/logs/desktop.log" || echo '(none)'

sock="/run/user/$(id -u)/dsh-desktop-$(id -u)-$PORT.sock"
echo "=== socket: $sock ==="
ask () {
  python3 - "$sock" "$1" <<'PY'
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
try:
    s.connect(sys.argv[1])
    s.sendall(('js ' + sys.argv[2]).encode('utf-8'))
    data = b''
    while True:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
    print(data.decode('utf-8', 'replace').strip())
except Exception as exc:
    print('ERR', exc)
finally:
    try:
        s.close()
    except Exception:
        pass
PY
}

for expr in \
  "String(!!window.__dshPan)" \
  "String(!!window.__dshMenu)" \
  "String(!!window.__dshTextMenu)" \
  "String(!!window.__dshDragOutLinux)" \
  "String(typeof window.__DSH_HOST_PATHS__)" \
  "String(document.querySelectorAll('li[data-files-entry]').length)"; do
  printf '%-46s -> ' "$expr"
  ask "$expr"
done
