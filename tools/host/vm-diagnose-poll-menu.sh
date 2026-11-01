#!/bin/bash
# 1) 清掉残留的桥进程
# 2) 看 Plasma 的剪贴板服务（klipper）有没有 DBus 接口 —— 有这个就不用反复连 Wayland
# 3) 复现：菜单弹出后，后台跑 wl-paste 轮询，看菜单是不是被顶掉
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"

echo '== 1. 残留进程'
pgrep -af 'vm-watch|vm-apply' | head -5 || echo '  （没有）'
pkill -f 'vm-watch.py' 2>/dev/null
pkill -f 'vm-apply.py' 2>/dev/null
pkill -f 'vm-menu-survive.py' 2>/dev/null
sleep 0.5

echo '== 2. klipper DBus'
command -v gdbus || echo '  gdbus 缺失'
timeout 8 gdbus introspect --session --dest org.kde.klipper --object-path /klipper 2>&1 | head -25 || echo '  org.kde.klipper 不可用'
echo '--- 读剪贴板（DBus）'
timeout 8 gdbus call --session --dest org.kde.klipper --object-path /klipper \
  --method org.kde.klipper.getClipboardContents 2>&1 | head -3 || echo '  读失败'

echo '== 3. 菜单存活 vs wl-paste 轮询'
kscreen-doctor --dpms on >/dev/null 2>&1
setsid nohup python3 -u /tmp/vm-menu-survive.py >/tmp/menu-survive.log 2>&1 &
sleep 2.2
python3 /tmp/vm-shot.py /tmp/s-1.png >/dev/null 2>&1
echo '  [基线] 菜单已弹出，抓 1 帧'
( while :; do wl-paste --no-newline >/dev/null 2>&1; sleep 0.35; done ) &
LOOP=$!
sleep 0.6
python3 /tmp/vm-shot.py /tmp/s-2.png >/dev/null 2>&1
sleep 1.2
python3 /tmp/vm-shot.py /tmp/s-3.png >/dev/null 2>&1
kill $LOOP 2>/dev/null
python3 - <<'PY'
from PIL import Image
import numpy as np
def load(p):
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.int16)
a, b, c = load('/tmp/s-1.png'), load('/tmp/s-2.png'), load('/tmp/s-3.png')
for x, y, l in ((a, b, '基线 vs 轮询 0.6s'), (b, c, '0.6s vs 1.8s')):
    d = np.abs(x - y); ys, xs = np.where(d.sum(axis=2) > 12)
    print('  %-18s changed=%-5d box=%s' % (l, len(xs), (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None))
PY
pkill -f vm-menu-survive.py 2>/dev/null
echo '== 完成'
