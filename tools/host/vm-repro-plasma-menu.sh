#!/bin/bash
# 决定性复现：弹出 Plasma 自己的菜单（Klipper 的弹出菜单），然后跑 wl-paste 轮询，
# 看菜单会不会被顶掉。同时验证 klipper 的 DBus 读写能不能替代 wl-clipboard。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
K="org.kde.klipper.klipper"

echo '== A. DBus 读剪贴板'
timeout 8 gdbus call --session --dest org.kde.klipper --object-path /klipper --method $K.getClipboardContents 2>&1 | head -2

echo '== B. DBus 写剪贴板，再用 wl-paste 校验'
timeout 8 gdbus call --session --dest org.kde.klipper --object-path /klipper --method $K.setClipboardContents "dbus-write-test" 2>&1 | head -2
sleep 0.5
printf '  wl-paste 读到: %s\n' "$(timeout 5 wl-paste --no-newline 2>/dev/null)"

echo '== C. 弹出 Plasma 菜单'
kscreen-doctor --dpms on >/dev/null 2>&1
timeout 5 gdbus call --session --dest org.kde.klipper --object-path /klipper --method $K.showKlipperPopupMenu 2>&1 | head -2
sleep 0.7
python3 /tmp/vm-shot.py /tmp/k-1.png >/dev/null 2>&1
echo '  [菜单已弹，抓一帧]'

echo '== D. 开始 wl-paste 轮询（350ms 一次），再抓帧'
( while :; do wl-paste --no-newline >/dev/null 2>&1; sleep 0.35; done ) &
LOOP=$!
sleep 1.0
python3 /tmp/vm-shot.py /tmp/k-2.png >/dev/null 2>&1
sleep 1.2
python3 /tmp/vm-shot.py /tmp/k-3.png >/dev/null 2>&1
kill $LOOP 2>/dev/null

echo '== E. 关掉菜单（再点一次 DBus 菜单）'
timeout 5 gdbus call --session --dest org.kde.klipper --object-path /klipper --method $K.showKlipperPopupMenu >/dev/null 2>&1

python3 - <<'PY'
from PIL import Image
import numpy as np
def load(p):
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.int16)
a, b, c = load('/tmp/k-1.png'), load('/tmp/k-2.png'), load('/tmp/k-3.png')
for x, y, l in ((a, b, '菜单 vs 轮询1s'), (b, c, '轮询1s vs 2.2s')):
    d = np.abs(x - y); ys, xs = np.where(d.sum(axis=2) > 12)
    print('  %-16s changed=%-5d box=%s' % (l, len(xs), (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None))
PY
echo '== done'
