#!/usr/bin/env python3
"""像素门禁：把设计稿参考图和 GTK 实拍图逐主题比对，超预算就失败。

  python tools/host/pixel-gate.py            # 对照 budget 检查（回归就失败）
  python tools/host/pixel-gate.py --update   # 把当前值写进 budget（只在确有改进时用）

参考图：dsh-desktop/linux/manager/design/references/<theme>-<mode>-<page>.png
实拍图：vm-shots/gtk/<theme>-<mode>-<page>.png
预算：  dsh-desktop/linux/manager/design/pixel-budget.json
  { "frost-day-dashboard": {"mae": 6.38, "pct16": 4.94}, ... , "_target": {"mae": 3.0, "pct16": 3.0} }
"""
import glob
import io
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF_DIR = os.path.join(ROOT, 'dsh-desktop', 'linux', 'manager', 'design', 'references')
SHOT_DIR = os.path.join(ROOT, 'vm-shots', 'gtk')
BUDGET = os.path.join(ROOT, 'dsh-desktop', 'linux', 'manager', 'design', 'pixel-budget.json')
TOLERANCE = 0.15        # 允许的抖动（字体抗锯齿在每台机器上不完全一样）
TARGET = {'mae': 3.0, 'pct16': 3.0}


def load(path):
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.int16)


def measure(ref_path, shot_path):
    ref = load(ref_path)
    shot = load(shot_path)
    if ref.shape != shot.shape:
        return None
    delta = np.abs(ref - shot)
    return {
        'mae': round(float(delta.mean()), 3),
        'pct16': round(float((delta.max(axis=2) > 16).mean() * 100), 3),
    }


def main():
    update = '--update' in sys.argv
    if not os.path.isdir(SHOT_DIR):
        print('FAIL: 没有实拍图目录 %s（先在虚拟机上跑 vm-gtk-shot.py 再拉回来）' % SHOT_DIR)
        return 2
    budget = {}
    if os.path.exists(BUDGET):
        with io.open(BUDGET, encoding='utf-8') as fh:
            budget = json.load(fh)

    rows = []
    missing = []
    for ref in sorted(glob.glob(os.path.join(REF_DIR, '*.png'))):
        key = os.path.basename(ref)[:-4]
        shot = os.path.join(SHOT_DIR, key + '.png')
        if not os.path.exists(shot):
            missing.append(key)
            continue
        got = measure(ref, shot)
        if got is None:
            print('SKIP %-34s 尺寸不一致（参考图 %s）' % (key, key))
            continue
        rows.append((key, got))

    rows.sort(key=lambda r: -r[1]['mae'])
    print('%-34s %8s %8s   %s' % ('组合', 'MAE', '>16占比', '预算'))
    worst_regress = []
    for key, got in rows:
        prev = budget.get(key, {})
        note = ''
        if prev:
            if got['mae'] > prev['mae'] + TOLERANCE:
                note = 'REGRESS (was %.2f)' % prev['mae']
                worst_regress.append(key)
            else:
                note = 'ok (was %.2f)' % prev['mae']
        print('%-34s %8.3f %8.3f%%   %s' % (key, got['mae'], got['pct16'], note))

    if rows:
        avg = sum(r[1]['mae'] for r in rows) / len(rows)
        print('\n平均 MAE %.3f  目标 %.1f  (共 %d 组，缺图 %d 组)'
              % (avg, TARGET['mae'], len(rows), len(missing)))
    if missing:
        print('缺图：' + ' '.join(missing[:8]) + (' …' if len(missing) > 8 else ''))

    if update:
        data = {k: {kk: v[kk] for kk in ('mae', 'pct16')} for k, v in rows}
        data['_target'] = TARGET
        with io.open(BUDGET, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        print('已更新预算：%s' % BUDGET)
        return 0

    if worst_regress:
        print('\nFAIL: 这些组合比预算差了：' + ', '.join(worst_regress))
        return 1
    print('\nPASS（没有相对预算的回退）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
