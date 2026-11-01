#!/bin/bash
# 蓝色块到底是什么：取样 + 看安装版里按钮是怎么建的
set -u
echo "== 取样（安装版截图 /tmp/m146.png，窗口 1280 宽）=="
python3 - <<'PY'
from PIL import Image
im = Image.open('/tmp/m146.png').convert('RGB')
w, h = im.size
print('screenshot', w, h)
# 从右往左扫第一行高饱和像素，找蓝色块
for y in (18, 25, 32, 40):
    runs = []
    x = w - 8
    while x > w - 220:
        r, g, b = im.getpixel((x, y))
        if b > 180 and b - r > 60:          # 蓝色
            runs.append(x)
        x -= 1
    if runs:
        print('y=%d 蓝色像素 x范围 %d..%d 个数=%d' % (y, min(runs), max(runs), len(runs)))
        cx = (min(runs) + max(runs)) // 2
        print('   中心色:', im.getpixel((cx, y)))
        break
else:
    print('没找到明显的蓝色像素')
PY
echo "== 安装版 _window_button =="
grep -n -A8 "def _window_button" /usr/lib/dsh-manager/dsh_manager/gui.py | head -14
