#!/bin/bash
# 用 ydotool（uinput，内核级注入）真点一次右键，抓两帧看菜单会不会自己消失。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export YDOTOOL_SOCKET=/tmp/.ydotool_socket

echo '== 装 / 起 ydotool'
if ! command -v ydotool >/dev/null; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q ydotool 2>&1 | tail -3
fi
sudo pkill -x ydotoold 2>/dev/null
sleep 0.5
sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 1
ls -l /tmp/.ydotool_socket 2>/dev/null || { echo 'ydotoold 没起来'; cat /tmp/ydotoold.log; exit 1; }

kscreen-doctor --dpms on >/dev/null 2>&1
sleep 0.5
python3 /tmp/vm-shot.py /tmp/menu-0-before.png 2>&1 | tail -1

echo '== 右键（位置 700,430 = DSH 窗口正文区）'
ydotool mousemove 700 430
sleep 0.3
ydotool click 2
sleep 0.45
python3 /tmp/vm-shot.py /tmp/menu-1-after.png 2>&1 | tail -1
sleep 1.6
python3 /tmp/vm-shot.py /tmp/menu-2-later.png 2>&1 | tail -1
echo '== 两帧差异（越接近 0 说明画面没变；菜单若消失，差异会集中在菜单区域）'
python3 - <<'PY'
from PIL import Image, ImageChops
import itertools
a = Image.open('/tmp/menu-1-after.png').convert('RGB')
b = Image.open('/tmp/menu-2-later.png').convert('RGB')
diff = ImageChops.difference(a, b)
bbox = diff.getbbox()
import numpy as np
arr = np.asarray(diff, dtype=np.int16)
print('  bbox=%s  mean=%.4f  changed_px=%d' % (bbox, arr.mean(), (arr.sum(axis=2) > 12).sum()))
PY
