#!/bin/bash
# 把鼠标移开右上角再截图，验证那个蓝色小方块是不是"鼠标悬停在角落"触发的 KWin 提示。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
command -v kscreen-doctor >/dev/null && kscreen-doctor --dpms on >/dev/null 2>&1

if command -v xdotool >/dev/null; then
  xdotool mousemove 400 400 2>/dev/null && echo "鼠标移到 (400,400)"
fi
if command -v ydotool >/dev/null; then
  : # 若有 ydotool 也可用
fi
sleep 2
timeout 60 python3 /tmp/vm-shot.py /tmp/nohover.png 2>&1 | tail -1
python3 - <<'PY'
from PIL import Image
im = Image.open('/tmp/nohover.png').convert('RGB')
w, h = im.size
# 统计右上角 120x80 区域里"蓝色"像素（KWin 的图标是明亮蓝）
blue = 0
for y in range(0, 80):
    for x in range(w-160, w):
        r, g, b = im.getpixel((x, y))
        if b > 190 and b - r > 70 and g > 120:
            blue += 1
print('右上角蓝色像素数:', blue)
im.crop((1080, 0, 1280, 95)).resize((800, 380), Image.LANCZOS).save('/tmp/nohover-corner.png')
print('crop -> /tmp/nohover-corner.png')
PY
