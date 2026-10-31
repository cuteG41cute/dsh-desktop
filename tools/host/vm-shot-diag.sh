#!/bin/bash
# 截图三条路都试一遍，并报告每张的平均亮度（判断是不是纯黑）。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1); [ -n "${XA:-}" ] && export XAUTHORITY="$XA"

echo "== kwin 后端 =="
timeout 60 python3 /tmp/vm-shot.py /tmp/s-kwin.png kwin 2>&1 | tail -2
echo "== spectacle =="
if command -v spectacle >/dev/null; then
  timeout 60 spectacle -b -n -o /tmp/s-spec.png 2>&1 | tail -2
  ls -l /tmp/s-spec.png 2>/dev/null || echo "  spectacle 没出图"
else
  echo "  spectacle 未安装"
fi
echo "== 亮度 =="
python3 - <<'PY'
from PIL import Image
import os, statistics
for p in ('/tmp/s-kwin.png', '/tmp/s-spec.png', '/tmp/manager-awake.png'):
    if not os.path.exists(p):
        continue
    im = Image.open(p).convert('L')
    px = list(im.getdata())
    print('%-24s %dx%d mean=%.1f min=%d max=%d' % (os.path.basename(p), im.size[0], im.size[1],
          statistics.fmean(px), min(px), max(px)))
PY
