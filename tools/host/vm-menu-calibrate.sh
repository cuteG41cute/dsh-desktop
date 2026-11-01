#!/bin/bash
# 坐标校准 + 右键测试：
#  1) 悬停「新会话」按钮（真实 140,121），按钮背景会变 -> 证明绝对坐标可用
#  2) 右键输入框（真实 840,516），连抓 3 帧看有没有菜单
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
SOCK=/tmp/.ydotool_socket
pgrep -x ydotoold >/dev/null || sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 0.6
kscreen-doctor --dpms on >/dev/null 2>&1
shot() { python3 /tmp/vm-shot.py "$1" >/dev/null 2>&1; }
mv() { sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove -a "$1" "$2" >/dev/null 2>&1; }

python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3)
    s.connect('/run/user/1000/dsh-desktop-1000-3080.sock'); s.sendall(b'raise\n'); s.recv(64); s.close()
except Exception as e:
    print('raise 失败', e)
PY
sleep 1.0

echo '== 校准：指针移到空白处 -> 截一帧；移到「新会话」-> 再截一帧'
mv 700 200
sleep 0.5
shot /tmp/c-0.png
mv 140 121
sleep 0.7
shot /tmp/c-1.png

echo '== 右键输入框 (840,516)，连抓 3 帧'
mv 840 516
sleep 0.4
sudo YDOTOOL_SOCKET=$SOCK ydotool click 2 >/dev/null 2>&1
shot /tmp/c-2.png
shot /tmp/c-3.png
sleep 1.2
shot /tmp/c-4.png

python3 - <<'PY'
from PIL import Image
import numpy as np
def load(p):
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.int16)
a, b = load('/tmp/c-0.png'), load('/tmp/c-1.png')
d = np.abs(a - b); ys, xs = np.where(d.sum(axis=2) > 12)
print('  悬停校准: changed=%d box=%s' % (len(xs), (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None))
if len(xs):
    print('  悬停变化中心: (%d,%d)  —— 目标应该是 (140,121)' % (int(xs.mean()), int(ys.mean())))
base = b
for n in (2, 3, 4):
    arr = load('/tmp/c-%d.png' % n)
    d = np.abs(arr - base); ys, xs = np.where(d.sum(axis=2) > 12)
    print('  c-%d vs 右键前: changed=%-5d box=%s' % (n, len(xs), (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None))
PY
