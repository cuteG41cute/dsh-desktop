#!/bin/bash
# 点 DSH 页面里的下拉菜单，两帧比对：菜单是自己消失了，还是好好待着？
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
SOCK=/tmp/.ydotool_socket
pgrep -x ydotoold >/dev/null || sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 0.8
kscreen-doctor --dpms on >/dev/null 2>&1
shot() { python3 /tmp/vm-shot.py "$1" 2>&1 | tail -1; }

python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3)
    s.connect('/run/user/1000/dsh-desktop-1000-3080.sock'); s.sendall(b'raise\n'); s.recv(64); s.close()
except Exception as e:
    print('raise 失败', e)
PY
sleep 1.2
shot /tmp/dd-0.png

echo '== 点「标准模式」下拉'
sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove 537 372 >/dev/null 2>&1
sleep 0.3
sudo YDOTOOL_SOCKET=$SOCK ydotool click 1 >/dev/null 2>&1
sleep 0.5
shot /tmp/dd-1.png
sleep 1.6
shot /tmp/dd-2.png

python3 - <<'PY'
from PIL import Image
import numpy as np
a = np.asarray(Image.open('/tmp/dd-0.png').convert('RGB'), dtype=np.int16)
b = np.asarray(Image.open('/tmp/dd-1.png').convert('RGB'), dtype=np.int16)
c = np.asarray(Image.open('/tmp/dd-2.png').convert('RGB'), dtype=np.int16)
def cmp(x, y, label):
    d = np.abs(x - y)
    print('  %s: mean=%.4f changed=%d' % (label, d.mean(), (d.sum(axis=2) > 12).sum()))
cmp(a, b, '点之前 vs 点之后 0.5s')
cmp(b, c, '0.5s   vs      2.1s')
PY
echo '== 点空白关闭菜单'
sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove 900 200 >/dev/null 2>&1
sleep 0.2
sudo YDOTOOL_SOCKET=$SOCK ydotool click 1 >/dev/null 2>&1
