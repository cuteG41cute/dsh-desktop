#!/usr/bin/env python3
"""把 Linux 版的主题令牌（themes.json，14 套 × 25 个 token）生成成 WPF 资源字典。

Windows 版是独立实现，但**配色必须和 Linux 版逐像素一致**，所以这里不手抄颜色，
直接从 Linux 版已经验证过的 themes.json 生成 14 个 XAML 资源字典（7 主题 × 昼/夜）。

用法：
    python tools/gen-win-themes.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'dsh-desktop', 'linux', 'manager', 'dsh_manager', 'themes.json')
OUT = os.path.join(ROOT, 'dsh-manager-win', 'Themes')

# CSS token -> (XAML key, 类型)
COLORS = [
    ('bg', 'Bg'), ('bg2', 'Bg2'), ('app', 'App'), ('sidebar', 'Sidebar'),
    ('topbar', 'Topbar'), ('card', 'Card'), ('card-solid', 'CardSolid'),
    ('text', 'Text'), ('muted', 'Muted'), ('subtle', 'Subtle'),
    ('border', 'Border'), ('inner-border', 'InnerBorder'),
    ('accent', 'Accent'), ('accent2', 'Accent2'), ('accent-soft', 'AccentSoft'),
    ('on-accent', 'OnAccent'), ('hover', 'Hover'), ('success', 'Success'),
    ('danger', 'Danger'),
]
NUMBERS = [('radius', 'Radius'), ('app-radius', 'AppRadius'), ('blur', 'Blur')]


def parse_color(value):
    """CSS 颜色 -> WPF 颜色字面量 (#AARRGGBB)。支持 #rgb/#rrggbb 与 rgba()/rgb()。"""
    v = (value or '').strip()
    if not v:
        return None
    m = re.match(r'^#([0-9a-fA-F]{3,8})$', v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        if len(h) == 6:
            return '#FF' + h.upper()
        if len(h) == 8:
            return '#' + h.upper()
        return None
    m = re.match(r'^rgba?\(([^)]+)\)$', v)
    if m:
        parts = [p.strip() for p in m.group(1).split(',')]
        try:
            r, g, b = (int(float(p)) for p in parts[:3])
            a = float(parts[3]) if len(parts) > 3 else 1.0
        except Exception:
            return None
        return '#%02X%02X%02X%02X' % (max(0, min(255, int(round(a * 255)))), r, g, b)
    if v.lower() == 'white':
        return '#FFFFFFFF'
    if v.lower() == 'transparent':
        return '#00000000'
    return None


def parse_px(value):
    m = re.match(r'^\s*(-?[\d.]+)px\s*$', value or '')
    if m:
        return float(m.group(1))
    try:
        return float(value)
    except Exception:
        return 0.0


def parse_shadow(value):
    """CSS box-shadow -> (BlurRadius, ShadowDepth, Opacity, Color)。

    只取第一层（设计稿里的主阴影），WPF 没有多重阴影，用一层近似即可。
    CSS blur ≈ 2σ，WPF BlurRadius 也按 σ 的两倍解释，所以直接取数值。
    """
    if not value:
        return None
    first = value.split('),')[0]
    if not first.endswith(')'):
        first += ')'
    m = re.search(r'rgba?\(([^)]+)\)', first)
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split(',')]
    try:
        r, g, b = (int(float(p)) for p in parts[:3])
        a = float(parts[3]) if len(parts) > 3 else 1.0
    except Exception:
        return None
    nums = re.findall(r'(-?[\d.]+)(?:px)?\s', first + ' ')
    if len(nums) < 3:
        return None
    _x, y, blur = (float(n) for n in nums[:3])
    return (blur, y, a, '#FF%02X%02X%02X' % (r, g, b))


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    values = data['values']
    order = data['order']
    os.makedirs(OUT, exist_ok=True)

    written = []
    meta = []
    for key in sorted(values):
        theme, _, mode = key.partition('-')
        src = values[key]
        if theme not in order or mode not in ('day', 'night'):
            continue
        label = src.get('label') or theme
        lines = [
            '<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"',
            '                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"',
            '                    xmlns:sys="clr-namespace:System;assembly=mscorlib">',
            '    <!-- 由 tools/gen-win-themes.py 从 Linux 版 themes.json 生成，勿手改 -->',
        ]
        for css_key, xaml_key in COLORS:
            color = parse_color(src.get(css_key))
            if color:
                lines.append('    <Color x:Key="%s.Color">%s</Color>' % (xaml_key, color))
                lines.append('    <SolidColorBrush x:Key="%s" Color="%s" />' % (xaml_key, color))
        # 设计稿里的 "rgba(213,101,117,.07)" 这类派生色：alpha 放最高字节
        danger = parse_color(src.get('danger'))
        if danger and len(danger) == 9:
            lines.append('    <SolidColorBrush x:Key="DangerSoft" Color="#12%s" />' % danger[3:])
        success = parse_color(src.get('success'))
        if success and len(success) == 9:
            lines.append('    <SolidColorBrush x:Key="SuccessSoft" Color="#17%s" />' % success[3:])
        for css_key, xaml_key in NUMBERS:
            if css_key in src:
                value = parse_px(src[css_key])
                lines.append('    <sys:Double x:Key="%sValue">%g</sys:Double>'
                             % (xaml_key, value))
                lines.append('    <CornerRadius x:Key="%s">%g</CornerRadius>'
                             % (xaml_key, value))
        for css_key, xaml_key in (('shadow', 'WindowShadow'), ('card-shadow', 'CardShadow')):
            parsed = parse_shadow(src.get(css_key))
            if not parsed:
                continue
            blur, y, alpha, color = parsed
            if xaml_key == 'WindowShadow':
                # 设计稿里的 .app-shell 阴影是「铺满整页」用的（75px 模糊），当窗口投影会
                # 在四个圆角处糊成半透明尖角，而且被 14px 的外沿截断。窗口投影用一个收敛的小阴影。
                blur, y, alpha, color = 26.0, 6.0, 0.22, '#FF1F1B33'
            lines.append('    <DropShadowEffect x:Key="%s" x:Shared="False" BlurRadius="%g" '
                         'ShadowDepth="%g" Direction="270" Opacity="%g" Color="%s" />'
                         % (xaml_key, blur, y, alpha, color))
        if 'accent-rgb' in src:
            lines.append('    <sys:String x:Key="AccentRgb">%s</sys:String>' % src['accent-rgb'])
        lines.append('    <sys:String x:Key="ThemeId">%s</sys:String>' % theme)
        lines.append('    <sys:String x:Key="ThemeLabel">%s</sys:String>' % label)
        lines.append('    <sys:String x:Key="ThemeMode">%s</sys:String>' % mode)
        lines.append('</ResourceDictionary>')
        lines.append('')
        path = os.path.join(OUT, '%s-%s.xaml' % (theme, mode))
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('\n'.join(lines))
        written.append(path)
        meta.append((theme, mode, label))

    print('生成 %d 个主题字典 -> %s' % (len(written), OUT))
    for theme, mode, label in sorted(meta):
        print('  %-8s %-6s %s' % (theme, mode, label))
    return 0


if __name__ == '__main__':
    sys.exit(main())
