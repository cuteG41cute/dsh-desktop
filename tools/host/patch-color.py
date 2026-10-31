#!/usr/bin/env python3
"""在指定矩形里比较两张图的平均颜色 —— 定位"这块为什么不一样"的快速手段。

  python tools/host/patch-color.py REF.png SHOT.png x,y,w,h [x,y,w,h ...]
"""
import sys

import numpy as np
from PIL import Image


def main():
    ref_path, shot_path = sys.argv[1], sys.argv[2]
    ref = np.asarray(Image.open(ref_path).convert('RGB'), dtype=np.float32)
    shot = np.asarray(Image.open(shot_path).convert('RGB'), dtype=np.float32)
    for spec in sys.argv[3:]:
        x, y, w, h = (int(v) for v in spec.split(','))
        a = ref[y:y + h, x:x + w].reshape(-1, 3).mean(axis=0)
        b = shot[y:y + h, x:x + w].reshape(-1, 3).mean(axis=0)
        d = b - a
        print('%-22s 设计稿 rgb(%3.0f,%3.0f,%3.0f)  GTK rgb(%3.0f,%3.0f,%3.0f)  Δ(%+.0f,%+.0f,%+.0f)'
              % (spec, *a, *b, *d))
    return 0


if __name__ == '__main__':
    sys.exit(main())
