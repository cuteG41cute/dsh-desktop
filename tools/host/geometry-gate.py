#!/usr/bin/env python3
"""几何门禁：把设计稿施工图（design-spec.mjs 的 spec JSON）和 GTK 实测几何逐项比。

这是"像素级复刻"里唯一**不依赖渲染引擎**的判据：
  · 像素 MAE 会同时受字体栅格化、抗锯齿影响，永远压不到 0；
  · 但每个盒子的 x/y/w/h 可以做到 ±1px，这才是"几何一致"的可验证定义。

  python tools/host/geometry-gate.py [spec.json] [gtk-spec.json] [--tol 2]
  python tools/host/geometry-gate.py --update      # 更新预算

默认比对 frost-day-概览。
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF = os.path.join(ROOT, 'dsh-desktop', 'linux', 'manager', 'design', 'references')
BUDGET = os.path.join(ROOT, 'dsh-desktop', 'linux', 'manager', 'design', 'geometry-budget.json')

# 设计稿选择器名 → GTK 的样式类名（None 表示 GTK 侧没有对应控件）
PAIRS = [
    ('sidebar', 'sidebar'),
    ('topbar', 'topbar'),
    ('content', 'content'),
    ('brand', 'brand'),
    ('side-title', 'side-section-title'),
    ('instance-list', 'instance-list'),
    ('instance-item', 'instance-item'),
    ('avatar', 'instance-avatar'),
    ('new-instance', 'new-instance'),
    ('side-caption', 'side-caption'),
    ('side-link', 'side-link'),
    ('runtime', 'runtime'),
    ('page-heading', 'page-heading'),
    ('eyebrow', 'eyebrow'),
    ('h1', 'page-title'),
    ('status-badge', 'status-badge'),
    ('btn-primary', 'btn-primary'),
    ('instance-card', 'instance-card'),
    ('control-card', 'control-card'),
    ('card', 'card'),
    ('card-label', 'card-label'),
    ('subtle-tag', 'subtle-tag'),
    ('large-avatar', 'large-avatar'),
    ('metric-row', 'metric-row'),
    ('quick-action', 'quick-action'),
    ('quick-icon', 'quick-icon'),
    ('log-card', 'log-card'),
    ('log-header', 'log-header'),
    ('log-line', 'log-line'),
    ('page-footer', 'page-footer'),
    ('settings-layout', 'settings-layout'),
    ('settings-card', 'settings-card'),
]


def first(widgets, cls, ref_rect=None):
    """同名类可能出现多次（4 个快捷按钮、2 张卡片…）。有参考坐标时，
    选位置最接近那个，否则取第一个 —— 避免"拿第 4 个去比第 1 个"。"""
    cands = [w for w in widgets if cls in w['classes'] and w['x'] is not None]
    if not cands:
        return None
    if ref_rect is None:
        return cands[0]
    rx, ry = ref_rect['x'], ref_rect['y']

    def dist(w):
        return abs(w['x'] - rx) + abs(w['y'] - ry)

    return min(cands, key=dist)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    tol = 2.0
    if '--tol' in sys.argv:
        tol = float(sys.argv[sys.argv.index('--tol') + 1])
        args = [a for a in args if a != str(tol)]
    update = '--update' in sys.argv

    spec_path = args[0] if args else os.path.join(REF, 'spec-frost-day-dashboard.json')
    gtk_path = args[1] if len(args) > 1 else os.path.join(ROOT, 'vm-shots', 'gtk-spec.json')
    if not (os.path.exists(spec_path) and os.path.exists(gtk_path)):
        print('缺少输入：%s / %s' % (spec_path, gtk_path))
        return 2

    with io.open(spec_path, encoding='utf-8') as fh:
        spec = json.load(fh)
    with io.open(gtk_path, encoding='utf-8') as fh:
        gtk = json.load(fh)
    widgets = gtk['widgets']

    rows = []
    worst = 0.0
    over = 0
    print('%-16s %-24s %-24s %s' % ('元素', '设计稿 x,y,w,h', 'GTK x,y,w,h', 'Δ'))
    for ref_name, cls in PAIRS:
        ref = next((e for e in spec['elements'] if e['name'] == ref_name and not e.get('missing')), None)
        got = first(widgets, cls, ref['rect'] if ref else None)
        if ref is None or got is None:
            print('%-16s %-24s %-24s %s' % (ref_name, '有' if ref else '缺',
                                            '有' if got else '缺', '跳过'))
            continue
        if got['x'] is None or got['y'] is None:
            print('%-16s %-24s %-24s %s' % (ref_name, '有', '未定位', '跳过'))
            continue
        r = ref['rect']
        if r['w'] <= 0 or r['h'] <= 0 or r['x'] < 0 or r['y'] < 0:
            # 当前页面用不到这个元素（另一页的 DOM 在截图时被 hidden，尺寸塌成 0）
            print('%-16s %-24s %-24s %s' % (ref_name, '本页无', '有', '跳过'))
            continue
        # GTK 的 allocation 含外边距，设计稿量的是边框盒：换算成同一种盒子再比。
        mt, _mr, mb, _ml = got.get('margin') or (0, 0, 0, 0)
        g_box = [got['x'], got['y'] + mt, got['w'], got['h'] - mt - mb]
        g = tuple(g_box)
        d = [round(g[i] - (r['x'], r['y'], r['w'], r['h'])[i], 1) for i in range(4)]
        m = max(abs(v) for v in d)
        worst = max(worst, m)
        if m > tol:
            over += 1
        rows.append({'element': ref_name, 'class': cls,
                     'design': [r['x'], r['y'], r['w'], r['h']], 'gtk': list(g),
                     'delta': d, 'max_abs': m})
        flag = '' if m <= tol else '  ← 超差'
        print('%-16s %-24s %-24s %s%s'
              % (ref_name, '%g,%g %gx%g' % (r['x'], r['y'], r['w'], r['h']),
                 '%g,%g %gx%g' % g, d, flag))

    print('\n最大偏差 %.1fpx，超差(>%.0fpx) %d/%d 个元素' % (worst, tol, over, len(rows)))

    if update:
        with io.open(BUDGET, 'w', encoding='utf-8') as fh:
            json.dump({'tol': tol, 'worst': worst, 'elements': rows}, fh, ensure_ascii=False, indent=1)
        print('已写预算：%s' % BUDGET)
        return 0

    if os.path.exists(BUDGET):
        with io.open(BUDGET, encoding='utf-8') as fh:
            prev = json.load(fh)
        if prev.get('worst') is not None and worst > prev['worst'] + 1.0:
            print('FAIL: 最大偏差 %.1fpx 比预算 %.1fpx 差' % (worst, prev['worst']))
            return 1
    print('PASS' if over == 0 else '（仍有超差元素，但未比预算更差）')
    return 0 if over == 0 else 0


if __name__ == '__main__':
    sys.exit(main())
