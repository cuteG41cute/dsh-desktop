#!/usr/bin/env python3
"""把 design/index.html 里的 SVG 图标（<symbol id="i-*">）转成 WPF 的 PathGeometry 资源。

Windows 版是**独立实现**，但它必须和 Linux 版长得一模一样，所以图标的矢量路径直接
从设计稿里取（设计稿是这个项目的视觉真理），不手抄、不重画。

用法：
    python tools/gen-win-icons.py            # 写 dsh-manager-win/Themes/Icons.xaml
    python tools/gen-win-icons.py --list     # 只列图标名
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'dsh-desktop', 'linux', 'manager', 'design', 'index.html')
OUT = os.path.join(ROOT, 'dsh-manager-win', 'Themes', 'Icons.xaml')

SYMBOL_RE = re.compile(r'<symbol[^>]*id="(i-[^"]+)"[^>]*>(.*?)</symbol>', re.S)
CMD_RE = re.compile(r'[MmLlHhVvCcSsQqTtAaZz][^MmLlHhVvCcSsQqTtAaZz]*')

ATTR_RE = r'\b%s="([^"]*)"'


def _attr(tag, name):
    m = re.search(ATTR_RE % name, tag)
    return m.group(1) if m else None


def _num(tag, name, default=0.0):
    v = _attr(tag, name)
    return float(v) if v is not None else default


def rect_path(tag):
    x, y = _num(tag, 'x'), _num(tag, 'y')
    w, h = _num(tag, 'width'), _num(tag, 'height')
    r = max(_num(tag, 'rx', _num(tag, 'ry', 0)), _num(tag, 'ry', 0))
    r = min(r, w / 2, h / 2)
    if r <= 0:
        return 'M%g %g H%g V%g H%g Z' % (x, y, x + w, y + h, x)
    return ('M%g %g H%g A%g %g 0 0 1 %g %g V%g A%g %g 0 0 1 %g %g H%g '
            'A%g %g 0 0 1 %g %g V%g A%g %g 0 0 1 %g %g Z'
            % (x + r, y, x + w - r, r, r, x + w, y + r,
               y + h - r, r, r, x + w - r, y + h, x + r,
               r, r, x, y + h - r, y + r, r, r, x + r, y))


def circle_path(tag):
    cx, cy, r = _num(tag, 'cx'), _num(tag, 'cy'), _num(tag, 'r')
    if r <= 1.6:
        # 极小的圆在图标里是“点”（比如 i-more 的三个点）。我们用一条极短的圆头线
        # 代替：描边路径下看起来就是一个实心点，省得为它单独走 Fill。
        return 'M%g %g L%g %g' % (cx, cy, cx + 0.01, cy)
    return ('M%g %g A%g %g 0 1 0 %g %g A%g %g 0 1 0 %g %g Z'
            % (cx - r, cy, r, r, cx + r, cy, r, r, cx - r, cy))


def line_path(tag):
    return 'M%s %s L%s %s' % (_num(tag, 'x1'), _num(tag, 'y1'),
                              _num(tag, 'x2'), _num(tag, 'y2'))


def poly_path(tag, close):
    pts = [float(v) for v in (_attr(tag, 'points') or '').replace(',', ' ').split()]
    if len(pts) < 4:
        return ''
    parts = ['M%g %g' % (pts[0], pts[1])]
    for i in range(2, len(pts) - 1, 2):
        parts.append('L%g %g' % (pts[i], pts[i + 1]))
    if close:
        parts.append('Z')
    return ' '.join(parts)


def normalize(d):
    """把 SVG 路径规范成 WPF 迷你语言能吃的形式。

    WPF 的 AbbreviatedGeometryParser 比 SVG 严格：像 "M12 5v14M5 12h14" 这种
    命令字母紧贴数字、或数字紧贴下一个命令的写法会直接抛 FormatException，
    必须补空格（"M 12 5 v 14 M 5 12 h 14"）。
    """
    d = re.sub(r'(?<=[A-Za-z])(?=[-+.\d])', ' ', d)
    d = re.sub(r'(?<=[-+.\d])(?=[A-Za-z])', ' ', d)
    return re.sub(r'\s+', ' ', d).strip()


def path_data(body):
    """把一个 symbol 里所有形状拼成一个 Geometry 字符串（统一走描边）。

    设计稿里的图标混用 <path>/<rect>/<circle>/<line>，这里逐个转成路径指令；
    WPF 的迷你语言和 SVG 的 d 属性基本一致，所以只做形状转换、不改坐标。
    """
    parts = []
    for d in re.findall(r'\bd="([^"]+)"', body):
        parts.append(d.strip())
    for m in re.finditer(r'<rect([^>]*)/?>', body):
        parts.append(rect_path(m.group(1)))
    for m in re.finditer(r'<circle([^>]*)/?>', body):
        parts.append(circle_path(m.group(1)))
    for m in re.finditer(r'<line([^>]*)/?>', body):
        parts.append(line_path(m.group(1)))
    for m in re.finditer(r'<polyline([^>]*)/?>', body):
        parts.append(poly_path(m.group(1), False))
    for m in re.finditer(r'<polygon([^>]*)/?>', body):
        parts.append(poly_path(m.group(1), True))
    return normalize(' '.join(p for p in parts if p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', action='store_true')
    args = ap.parse_args()

    html = open(SRC, encoding='utf-8').read()
    icons = {}
    for name, body in SYMBOL_RE.findall(html):
        d = path_data(body)
        if d:
            icons[name] = d
    print('从设计稿读出 %d 个图标：%s' % (len(icons), ', '.join(sorted(icons))))
    if args.list:
        return 0
    if not icons:
        print('没解析到图标，检查 %s' % SRC, file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    lines = [
        '<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"',
        '                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">',
        '    <!-- 由 tools/gen-win-icons.py 从 design/index.html 自动生成，勿手改 -->',
    ]
    for name in sorted(icons):
        key = 'Icon.' + name[2:].replace('-', '_')
        lines.append('    <Geometry x:Key="%s">%s</Geometry>' % (key, icons[name]))
    lines.append('</ResourceDictionary>')
    lines.append('')
    with open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines))
    print('已写 %s（%d 个图标）' % (OUT, len(icons)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
