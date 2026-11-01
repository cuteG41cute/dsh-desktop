#!/bin/bash
# 直接看 ydotool 有没有真的移动指针：xdpyinfo/xdotool 拿不到 Wayland 指针，
# 所以用「把指针移到屏幕四角，看哪个窗口出现 hover 高亮」间接验证。
# 更可靠：把指针移到任务栏某个图标上，图标会高亮，截图能看出来。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
SOCK=/tmp/.ydotool_socket
pgrep -x ydotoold >/dev/null || sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 0.8
kscreen-doctor --dpms on >/dev/null 2>&1

echo '== 移到 (60,700)（任务栏最左的启动器图标）'
sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove -a 60 700
sleep 0.6
python3 /tmp/vm-shot.py /tmp/p-1.png 2>&1 | tail -1
echo '== 移到 (250,700)（任务栏中间的 Discord 图标附近）'
sudo YDOTOOL_SOCKET=$SOCK ydotool mousemove -a 250 700
sleep 0.6
python3 /tmp/vm-shot.py /tmp/p-2.png 2>&1 | tail -1
python3 - <<'PY'
from PIL import Image
import numpy as np
a = np.asarray(Image.open('/tmp/p-1.png').convert('RGB'), dtype=np.int16)
b = np.asarray(Image.open('/tmp/p-2.png').convert('RGB'), dtype=np.int16)
d = np.abs(a - b)
ys, xs = np.where(d.sum(axis=2) > 12)
print('  两帧差异: changed=%d box=%s' % (len(xs), (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None))
PY
echo '== 版本信息'
ydotool --version 2>&1 | head -2 || true
cat /tmp/ydotoold.log 2>/dev/null | head -5
