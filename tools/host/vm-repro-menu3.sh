#!/bin/bash
# 右键点 DSH 输入框，抓 0.3s / 1.5s / 3s 三帧，看菜单是不是自己消失。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
SOCK=/tmp/.ydotool_socket
pgrep -x ydotoold >/dev/null || sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 0.8
kscreen-doctor --dpms on >/dev/null 2>&1

shot() { python3 /tmp/vm-shot.py "$1" 2>&1 | tail -1; }

sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove 700 430 >/dev/null 2>&1
sleep 0.4
shot /tmp/rc-0.png
sudo YDOTOOL_SOCKET=$SOCK ydotool click 2 >/dev/null 2>&1
sleep 0.30
shot /tmp/rc-1.png
sleep 1.2
shot /tmp/rc-2.png
sleep 1.5
shot /tmp/rc-3.png

python3 - <<'PY'
from PIL import Image, ImageChops
import numpy as np
imgs = {n: Image.open('/tmp/rc-%s.png' % n).convert('RGB') for n in ('0', '1', '2', '3')}
base = np.asarray(imgs['0'], dtype=np.int16)
for n in ('1', '2', '3'):
    arr = np.asarray(imgs[n], dtype=np.int16)
    d = np.abs(arr - base)
    print('  vs 右键前  %s: mean=%.4f changed=%d' % (n, d.mean(), (d.sum(axis=2) > 12).sum()))
d = np.abs(np.asarray(imgs['2'], dtype=np.int16) - np.asarray(imgs['1'], dtype=np.int16))
print('  1 vs 2（菜单若已消失，这里差异会很大）: mean=%.4f changed=%d' % (d.mean(), (d.sum(axis=2) > 12).sum()))
PY
echo '== 菜单那几帧的位置（差异框）'
python3 - <<'PY'
from PIL import Image, ImageChops
a = Image.open('/tmp/rc-1.png').convert('RGB')
b = Image.open('/tmp/rc-0.png').convert('RGB')
print('  右键后差异框:', ImageChops.difference(a, b).getbbox())
PY
