#!/bin/bash
# 修正坐标（截图预览是 1066 宽，真实是 1280：乘 1.2）
#   下拉「标准模式」预览(537,372) -> 真实(644,446)
#   输入框       预览(700,430) -> 真实(840,516)
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
SOCK=/tmp/.ydotool_socket
pgrep -x ydotoold >/dev/null || sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 0.8
kscreen-doctor --dpms on >/dev/null 2>&1
shot() { python3 /tmp/vm-shot.py "$1" 2>&1 | tail -1; }
click_at() { sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove "$1" "$2" >/dev/null 2>&1; sleep 0.25; sudo YDOTOOL_SOCKET=$SOCK ydotool click "${3:-1}" >/dev/null 2>&1; }

python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3)
    s.connect('/run/user/1000/dsh-desktop-1000-3080.sock'); s.sendall(b'raise\n'); s.recv(64); s.close()
except Exception as e:
    print('raise 失败', e)
PY
sleep 1.2

echo '== A. 点「标准模式」下拉 (644,446)'
shot /tmp/t-0.png
click_at 644 446
sleep 0.5
shot /tmp/t-1.png
sleep 1.8
shot /tmp/t-2.png
python3 - <<'PY'
from PIL import Image
import numpy as np
a = np.asarray(Image.open('/tmp/t-0.png').convert('RGB'), dtype=np.int16)
b = np.asarray(Image.open('/tmp/t-1.png').convert('RGB'), dtype=np.int16)
c = np.asarray(Image.open('/tmp/t-2.png').convert('RGB'), dtype=np.int16)
for x, y, l in ((a, b, '点击前 vs 点击后0.5s'), (b, c, '0.5s  vs 2.3s')):
    d = np.abs(x - y)
    ys, xs = np.where((d.sum(axis=2) > 12))
    box = (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None
    print('  %-18s mean=%.4f changed=%-6d box=%s' % (l, d.mean(), len(xs), box))
PY

echo '== B. 菜单还开着吗？再抓一帧比较'
sleep 0.5
shot /tmp/t-3.png
python3 - <<'PY'
from PIL import Image
import numpy as np
b = np.asarray(Image.open('/tmp/t-1.png').convert('RGB'), dtype=np.int16)
d = np.abs(np.asarray(Image.open('/tmp/t-3.png').convert('RGB'), dtype=np.int16) - b)
ys, xs = np.where((d.sum(axis=2) > 12))
print('  0.5s vs 3s: mean=%.4f changed=%d' % (d.mean(), len(xs)))
PY

echo '== C. 关掉菜单（点空白）'
click_at 1000 250
