#!/bin/bash
# 用 kscreen-doctor 打开 DPMS（Plasma 6 空闲后会关屏，portal/kwin 截图全是纯黑），再截图。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0

if command -v kscreen-doctor >/dev/null; then
  echo "== 输出列表 =="
  kscreen-doctor -o 2>&1 | grep -E 'Output|enabled|dpms|connected' | head -6
  echo "== 打开 DPMS =="
  kscreen-doctor --dpms on 2>&1 | tail -2
else
  echo "kscreen-doctor 未安装"
fi
sleep 3
echo "== 截图 =="
timeout 60 python3 /tmp/vm-shot.py /tmp/manager-dpms.png 2>&1 | tail -2
python3 - <<'PY'
from PIL import Image
import statistics, os
p = '/tmp/manager-dpms.png'
if os.path.exists(p):
    im = Image.open(p).convert('L')
    px = list(im.getdata())
    print('亮度 mean=%.1f max=%d' % (statistics.fmean(px), max(px)))
PY
