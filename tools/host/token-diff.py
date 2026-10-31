#!/usr/bin/env python3
"""把设计稿真值（design/references/tokens.json）和管理器生成的主题令牌逐项比对。

  python tools/host/token-diff.py            # 只报告差异
  python tools/host/token-diff.py --strict   # 有差异即非零退出（给门禁用）

为什么需要：crystal/alpine 夜间 pixel diff 特别大，逐像素看不出是哪个颜色错，
这里直接把 29 个 CSS 变量拧出来比，一眼能定位。
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESIGN = os.path.join(ROOT, 'dsh-desktop', 'linux', 'manager', 'design', 'references', 'tokens.json')
THEMES = os.path.join(ROOT, 'dsh-desktop', 'linux', 'manager', 'dsh_manager', 'themes.json')

# 只比色值类令牌；font/orb-filter/blur 这类是设计稿的 CSS 手段，GTK 侧不一一对应
COLOUR_KEYS = ('bg', 'bg2', 'app', 'sidebar', 'topbar', 'card', 'card-solid', 'text',
               'muted', 'subtle', 'border', 'inner-border', 'accent', 'accent2',
               'accent-soft', 'on-accent', 'success', 'danger', 'hover')


def norm(value):
    """把 rgba(121,104,232,.1) / #7968e8 / rgb(121,104,232) 归一成可比较的元组。"""
    v = (value or '').strip().lower().replace(' ', '')
    if not v:
        return None
    m = re.match(r'^#([0-9a-f]{6})$', v)
    if m:
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    m = re.match(r'^#([0-9a-f]{3})$', v)
    if m:
        h = m.group(1)
        return (int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16), 1.0)
    m = re.match(r'^rgba?\(([^)]+)\)$', v)
    if m:
        parts = [p for p in re.split('[,/]', m.group(1)) if p]
        try:
            r, g, b = (int(float(parts[i])) for i in range(3))
        except (IndexError, ValueError):
            return None
        a = float(parts[3]) if len(parts) > 3 else 1.0
        return (r, g, b, round(a, 3))
    return None


def close(a, b, tol=2.0, atol=0.02):
    if a is None or b is None:
        return False
    return all(abs(a[i] - b[i]) <= tol for i in range(3)) and abs(a[3] - b[3]) <= atol


def main():
    strict = '--strict' in sys.argv
    with io.open(DESIGN, encoding='utf-8') as fh:
        design = json.load(fh)['values']
    with io.open(THEMES, encoding='utf-8') as fh:
        themes = json.load(fh)['values']

    problems = 0
    total = 0
    per_combo = []
    for combo in sorted(design):
        want = design[combo]
        got = themes.get(combo, {})
        bad = []
        for key in COLOUR_KEYS:
            if key not in want:
                continue
            total += 1
            wv, gv = norm(want[key]), norm(got.get(key, ''))
            if not close(wv, gv):
                bad.append((key, want[key], got.get(key, '—')))
        if bad:
            problems += len(bad)
            per_combo.append((combo, bad))

    print('比对了 %d 个色值令牌，%d 个不一致，涉及 %d 个组合'
          % (total, problems, len(per_combo)))
    for combo, bad in per_combo:
        print('\n[%s]' % combo)
        for key, want, got in bad[:12]:
            print('  %-13s 设计稿 %-26s 管理器 %s' % (key, want, got))
        if len(bad) > 12:
            print('  …还有 %d 项' % (len(bad) - 12))

    if strict and problems:
        print('\nFAIL: 主题令牌与设计稿不一致')
        return 1
    print('\n%s' % ('PASS' if not problems else '（仅报告）'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
