"""Patch 15: 设置页左列要抢宽度（设计稿 639，右列固定 426），顺手把 CSS 检查器的误报修掉。"""
import io
import re

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'
CHECK = 'dsh-desktop/linux/manager/tools/theme-token-check.py'

GUI_SUBS = [
    ("        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)",
     "        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)\n"
     "        left.set_hexpand(True)   # 设计稿左列 639、右列固定 426"),
]


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in GUI_SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    # CSS 注释里出现 "gap:" 被检查器当成了属性 → 改词，并让检查器先剥注释
    c = io.open(CSS, encoding='utf-8').read()
    c = c.replace('/* 设置页（设计稿 .settings-card{padding:21px}、.settings-layout{gap:17px}） */',
                  '/* 设置页（设计稿 .settings-card padding 21px；两列之间留 17px） */')
    io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c)

    k = io.open(CHECK, encoding='utf-8').read()
    if 'strip_css_comments' not in k:
        k = k.replace('def main():',
                      'def strip_css_comments(text):\n'
                      '    """检查 GTK 不认的属性前，先把 /* */ 注释剥掉（否则注释里的\n'
                      '    `gap:` 之类会被误报成属性）。"""\n'
                      '    return re.sub(r"/\\*.*?\\*/", "", text, flags=re.S)\n\n\n'
                      'def main():', 1)
        # 在读取 css 文本后剥注释：找最常见的读取变量名
        k = re.sub(r"(\n\s*)(css|text|src)\s*=\s*io\.open\([^\n]+\)\.read\(\)",
                   lambda m: '%s%s = strip_css_comments(io.open(%s).read())'
                             % (m.group(1), m.group(2),
                                re.search(r'io\.open\(([^\n]+?)\)\.read', m.group(0)).group(1)),
                   k, count=1)
        io.open(CHECK, 'w', encoding='utf-8', newline='\n').write(k)
    print('gui patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
