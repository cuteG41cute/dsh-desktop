#!/usr/bin/env python3
"""估两张图之间的整体位移（dx, dy）—— 用来判断"是不是整体错位了"。

做法：在 ±12px 范围内把实拍图平移，找 MAE 最小的位移。位移不为 0 说明
两边的锚点（比如顶栏高度）不同，先把锚点对齐再谈细节。

  python tools/host/align-shift.py REF.png SHOT.png [range]
"""
import sys

import numpy as np
from PIL import Image


def load(path):
    return np.asarray(Image.open(path).convert('L'), dtype=np.float32)


def main():
    ref_path, shot_path = sys.argv[1], sys.argv[2]
    rng = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    ref = load(ref_path)
    shot = load(shot_path)
    if ref.shape != shot.shape:
        print('size mismatch %s vs %s' % (ref.shape, shot.shape))
        return 2
    h, w = ref.shape
    best = None
    for dy in range(-rng, rng + 1):
        for dx in range(-rng, rng + 1):
            y0, y1 = max(0, dy), min(h, h + dy)
            x0, x1 = max(0, dx), min(w, w + dx)
            a = ref[y0:y1, x0:x1]
            b = shot[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
            mae = float(np.abs(a - b).mean())
            if best is None or mae < best[0]:
                best = (mae, dx, dy)
    base = float(np.abs(ref - shot).mean())
    print('位移最优 dx=%+d dy=%+d  MAE %.2f（未对齐 %.2f）' % (best[1], best[2], best[0], base))
    return 0


if __name__ == '__main__':
    sys.exit(main())
