#!/bin/bash
# 点下拉后**连续**抓 4 帧（不加 sleep），看看菜单是不是短暂出现又消失。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
SOCK=/tmp/.ydotool_socket
pgrep -x ydotoold >/dev/null || sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 0.8
kscreen-doctor --dpms on >/dev/null 2>&1

python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3)
    s.connect('/run/user/1000/dsh-desktop-1000-3080.sock'); s.sendall(b'raise\n'); s.recv(64); s.close()
except Exception as e:
    print('raise 失败', e)
PY
sleep 1.0
sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove -a 644 446
sleep 0.4
python3 /tmp/vm-shot.py /tmp/v-0.png >/dev/null 2>&1
sudo YDOTOOL_SOCKET=$SOCK ydotool click 1
for i in 1 2 3 4; do
  python3 /tmp/vm-shot.py /tmp/v-$i.png >/dev/null 2>&1
done
for i in 0 1 2 3 4; do
  echo "frame $i: $(stat -c%s /tmp/v-$i.png 2>/dev/null) bytes"
done
python3 - <<'PY'
from PIL import Image
import numpy as np
base = np.asarray(Image.open('/tmp/v-0.png').convert('RGB'), dtype=np.int16)
for i in (1, 2, 3, 4):
    try:
        arr = np.asarray(Image.open('/tmp/v-%d.png' % i).convert('RGB'), dtype=np.int16)
    except Exception:
        continue
    d = np.abs(arr - base)
    ys, xs = np.where(d.sum(axis=2) > 12)
    print('  v-%d vs v-0: changed=%-6d box=%s' % (i, len(xs), (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None))
PY
