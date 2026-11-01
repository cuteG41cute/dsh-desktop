#!/bin/bash
# ydotool 的 mousemove 默认是**相对**移动，必须加 -a 才是绝对坐标（踩过）。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
SOCK=/tmp/.ydotool_socket
pgrep -x ydotoold >/dev/null || sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 0.8
kscreen-doctor --dpms on >/dev/null 2>&1
shot() { python3 /tmp/vm-shot.py "$1" 2>&1 | tail -1; }
click_at() { sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove -a "$1" "$2" >/dev/null 2>&1; sleep 0.25; sudo YDOTOOL_SOCKET=$SOCK ydotool click "${3:-1}" >/dev/null 2>&1; }

python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3)
    s.connect('/run/user/1000/dsh-desktop-1000-3080.sock'); s.sendall(b'raise\n'); s.recv(64); s.close()
except Exception as e:
    print('raise 失败', e)
PY
sleep 1.2

echo '== 先确认鼠标真的到了 (644,446)：抓一帧看高亮'
click_at 644 446 1
sleep 0.5
shot /tmp/u-1.png
sleep 1.5
shot /tmp/u-2.png
python3 - <<'PY'
from PIL import Image
import numpy as np
b = np.asarray(Image.open('/tmp/u-1.png').convert('RGB'), dtype=np.int16)
c = np.asarray(Image.open('/tmp/u-2.png').convert('RGB'), dtype=np.int16)
d = np.abs(c - b)
ys, xs = np.where((d.sum(axis=2) > 12))
print('  0.5s vs 2s: mean=%.4f changed=%d box=%s' % (d.mean(), len(xs), (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None))
PY

echo '== 右键输入框 (840,516)'
click_at 840 516 2
sleep 0.45
shot /tmp/u-3.png
sleep 1.5
shot /tmp/u-4.png
python3 - <<'PY'
from PIL import Image
import numpy as np
a = np.asarray(Image.open('/tmp/u-1.png').convert('RGB'), dtype=np.int16)
b = np.asarray(Image.open('/tmp/u-3.png').convert('RGB'), dtype=np.int16)
c = np.asarray(Image.open('/tmp/u-4.png').convert('RGB'), dtype=np.int16)
for x, y, l in ((a, b, '右键前 vs 0.45s'), (b, c, '0.45s vs 2s')):
    d = np.abs(x - y); ys, xs = np.where((d.sum(axis=2) > 12))
    print('  %-16s mean=%.4f changed=%d box=%s' % (l, d.mean(), len(xs), (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None))
PY
echo '== 关掉任何菜单'
click_at 1100 620 1
