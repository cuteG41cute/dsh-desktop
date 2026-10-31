#!/usr/bin/env python3
"""区分"结构性误差"和"文字抗锯齿误差"。

做法：对两张图做轻度高斯模糊后再比一次。文字边缘的高频差异会被抹平，
如果 MAE 大幅下降，说明剩下的主要不是布局/配色问题，而是字体的栅格化差别
（Pango 的 hinting ≠ Chromium 的 subpixel 布局），那部分在 GTK 里补不平。

  python tools/host/diff-blur.py REF.png SHOT.png [radius]
"""
import sys

import numpy as np
from PIL import Image, ImageFilter


def load(path, blur=0.0):
    im = Image.open(path).convert('RGB')
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(im, dtype=np.float32)


def main():
    ref, shot = sys.argv[1], sys.argv[2]
    radius = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
    a = load(ref)
    b = load(shot)
    if a.shape != b.shape:
        print('size mismatch: %s vs %s' % (a.shape, b.shape))
        return 2
    sharp = float(np.abs(a - b).mean())
    ab = load(ref, radius)
    bb = load(shot, radius)
    soft = float(np.abs(ab - bb).mean())
    print('sharp MAE %.2f   blur(%.1f) MAE %.2f   高频占比 %.0f%%'
          % (sharp, radius, soft, (sharp - soft) / sharp * 100 if sharp else 0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
