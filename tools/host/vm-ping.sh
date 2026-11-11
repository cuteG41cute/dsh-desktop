#!/bin/bash
# 谁在监听控制套接字 / 窗口进程清单
set -u
sock="/run/user/$(id -u)/dsh-desktop-$(id -u)-3081.sock"
ls -l "$sock" 2>/dev/null || echo "(no socket)"
python3 - "$sock" <<'PY'
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(sys.argv[1])
    s.sendall(b'ping')
    print('socket pid:', s.recv(200).decode('utf-8', 'replace').strip())
except Exception as exc:
    print('ping ERR', exc)
PY
echo '--- window processes ---'
pgrep -a -f share/dsh-desktop | head -8
echo '--- lsof of socket ---'
sudo -n ss -xp 2>/dev/null | grep dsh-desktop | head -5 || true
