#!/bin/bash
# 通过控制套接字执行 JS，验证注入的 5 个增强是否都在（真正的窗口里）
set -u
PREFIX=/home/twinblade/.local/opt/deepseek-harness-2
PORT=3081

src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")
export GDK_BACKEND=x11

echo "=== 记录当前设置 ==="
cat "$HOME/.config/dsh-manager/settings.json" 2>/dev/null || echo '(无)'

echo "=== 关旧窗口，开新窗口（带 DEBUG）==="
pkill -f "share/dsh-desktop" 2>/dev/null || true
sleep 2
: > "$PREFIX/logs/desktop.log" 2>/dev/null || true
DSH_DESKTOP_DEBUG=1 dsh-manager --headless open --prefix "$PREFIX" 2>&1 | tail -2
sleep 10

echo "=== 注入日志 ==="
grep -a "injected" "$PREFIX/logs/desktop.log" | tail -6 || echo '(无)'

sock="${XDG_RUNTIME_DIR:-/run/user/1000}/dsh-desktop-$(id -u)-$PORT.sock"
echo "=== 控制套接字：$sock ==="
ls -l "$sock" 2>/dev/null || echo '(套接字不存在)'

ask () {
  python3 - "$sock" "$1" <<'PY'
import socket, sys
sock, expr = sys.argv[1], sys.argv[2]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(8)
try:
    s.connect(sock)
    s.sendall(('js ' + expr).encode('utf-8'))
    data = b''
    while True:
        chunk = s.recv(4096)
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
