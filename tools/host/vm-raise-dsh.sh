#!/bin/bash
# 把 DSH 桌面窗口提到前台，抓一帧，方便确定输入框位置。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
kscreen-doctor --dpms on >/dev/null 2>&1
python3 - <<'PY'
import socket
for p in ('/run/user/1000/dsh-desktop-1000-3080.sock',
          '/run/user/1000/dsh-desktop-1000-3081.sock'):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(p)
        s.sendall(b'raise\n')
        print(p, '->', s.recv(64))
        s.close()
    except Exception as exc:
        print(p, '-> 失败', exc)
PY
sleep 1.5
python3 /tmp/vm-shot.py /tmp/raised.png 2>&1 | tail -1
