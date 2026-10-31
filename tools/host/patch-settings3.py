"""Patch 16: 设置页列宽钉死 639/426，信息行按设计稿 40px 高。

设计稿：.settings-layout 两列 639 + 426（gap 17 = 1082）；
        .info-list>div{min-height:40px;border-bottom:1px solid inner-border}
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

GUI_SUBS = [
    ("        left.set_hexpand(True)   # 设计稿左列 639、右列固定 426",
     "        left.set_hexpand(True)\n        left.set_size_request(639, -1)   # 设计稿左列 639、右列 426"),
    ("            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)\n"
     "            name = self._label(key, 'metric-label')",
     "            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)\n"
     "            row.get_style_context().add_class('info-row')\n"
     "            name = self._label(key, 'metric-label')"),
]

CSS_TAIL = """
/* 设置页信息行（设计稿 .info-list>div：min-height 40、底部 1px 内边框） */
.info-row { min-height: 38px; border-bottom: 1px solid $(inner-border); }
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in GUI_SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    c = io.open(CSS, encoding='utf-8').read()
    if '.info-row' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
