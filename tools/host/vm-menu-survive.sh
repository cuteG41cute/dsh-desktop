#!/bin/bash
# 跑 vm-menu-survive.py 并在菜单弹出后连抓 3 帧，判断菜单是否会被「刷新掉」。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
kscreen-doctor --dpms on >/dev/null 2>&1
pkill -f vm-menu-survive.py 2>/dev/null
sleep 0.5
setsid nohup python3 -u /tmp/vm-menu-survive.py >/tmp/menu-survive.log 2>&1 &
sleep 2.6
python3 /tmp/vm-shot.py /tmp/m-1.png 2>&1 | tail -1
sleep 1.4
python3 /tmp/vm-shot.py /tmp/m-2.png 2>&1 | tail -1
sleep 2.0
python3 /tmp/vm-shot.py /tmp/m-3.png 2>&1 | tail -1
echo '== 程序输出'
cat /tmp/menu-survive.log
echo '== 帧间差异（菜单若消失，差异会很大）'
python3 - <<'PY'
from PIL import Image
import numpy as np
def load(p):
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.int16)
a, b, c = load('/tmp/m-1.png'), load('/tmp/m-2.png'), load('/tmp/m-3.png')
for x, y, l in ((a, b, 'm-1 vs m-2 (1.4s)'), (b, c, 'm-2 vs m-3 (2s)')):
    d = np.abs(x - y); ys, xs = np.where(d.sum(axis=2) > 12)
    print('  %-20s changed=%-5d box=%s' % (l, len(xs), (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None))
PY
pkill -f vm-menu-survive.py 2>/dev/null
echo done
