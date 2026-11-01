#!/bin/bash
# 同上，但客户端用 root 跑（ydotool 的 socket 是 root-only）。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
SOCK=/tmp/.ydotool_socket

pgrep -x ydotoold >/dev/null || sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 1
kscreen-doctor --dpms on >/dev/null 2>&1

shot() { python3 /tmp/vm-shot.py "$1" 2>&1 | tail -1; }

echo '== 把指针移开，先抓一帧基线'
sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove 300 620 2>&1 | head -2
sleep 0.4
shot /tmp/menu-0-before.png

echo '== 右键点 DSH 聊天输入区 (700,560)'
sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove 700 560 2>&1 | head -2
sleep 0.3
sudo YDOTOOL_SOCKET=$SOCK ydotool click 2 2>&1 | head -2
sleep 0.35
shot /tmp/menu-1-after.png
sleep 1.5
shot /tmp/menu-2-later.png

echo '== 差异'
python3 - <<'PY'
from PIL import Image, ImageChops
import numpy as np
for name in ('menu-0-before', 'menu-1-after', 'menu-2-later'):
    pass
a = Image.open('/tmp/menu-1-after.png').convert('RGB')
b = Image.open('/tmp/menu-2-later.png').convert('RGB')
d = ImageChops.difference(a, b)
arr = np.asarray(d, dtype=np.int16)
print('  1s 后: bbox=%s mean=%.4f changed=%d' % (d.getbbox(), arr.mean(), (arr.sum(axis=2) > 12).sum()))
base = Image.open('/tmp/menu-0-before.png').convert('RGB')
d2 = ImageChops.difference(base, a)
a2 = np.asarray(d2, dtype=np.int16)
print('  右键前后: bbox=%s mean=%.4f changed=%d' % (d2.getbbox(), a2.mean(), (a2.sum(axis=2) > 12).sum()))
PY
