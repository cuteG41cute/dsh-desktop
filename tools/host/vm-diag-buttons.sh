#!/bin/bash
# 1) 安装包里有没有三个窗口图标 2) 截图上那个蓝色块到底是什么颜色
set -u
echo "== 安装目录里的图标 =="
ls /usr/lib/dsh-manager/dsh_manager/icons/ | grep -E 'maximize|minus|restore|^x\.svg' || echo "（没有匹配）"
echo "== 尺寸/校验 =="
for f in minus maximize restore; do
  p="/usr/lib/dsh-manager/dsh_manager/icons/$f.svg"
  if [ -f "$p" ]; then
    printf '%-10s %s bytes\n' "$f" "$(stat -c%s "$p")"
  else
    printf '%-10s MISSING\n' "$f"
  fi
done
echo "== 安装版 gui.py 里 max 按钮的写法 =="
grep -n "maximize" /usr/lib/dsh-manager/dsh_manager/gui.py | head -5
echo "== 截图蓝块取样 =="
python3 - <<'PY'
from PIL import Image
im = Image.open('/tmp/m146.png').convert('RGB')
for name, box in (('max 按钮中心', (1125, 25, 1140, 40)),
                  ('min 按钮中心', (1100, 25, 1115, 40)),
                  ('close 按钮', (1160, 25, 1175, 40))):
    crop = im.crop(box)
    px = list(crop.getdata())
    avg = tuple(sum(c[i] for c in px) // len(px) for i in range(3))
    print('%-12s avg=%s' % (name, avg))
PY
