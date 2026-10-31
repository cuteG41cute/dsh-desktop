"""Patch 14: 设置页对齐设计稿（类名/列宽/间距/内边距）。

设计稿：.settings-layout{grid-template-columns: 1.5fr 1fr; gap:17px}
        .settings-layout>div{display:flex;flex-direction:column;gap:17px}
        .settings-card{padding:21px}
实测：1082 = 639 + 17 + 426。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

GUI_SUBS = [
    ("        grid = Gtk.Grid(column_spacing=16, row_spacing=16)\n"
     "        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)",
     "        # 设计稿 .settings-layout：两列 1.5fr/1fr，间距 17（1082 = 639 + 17 + 426）\n"
     "        grid = Gtk.Grid(column_spacing=17, row_spacing=17)\n"
     "        grid.get_style_context().add_class('settings-layout')\n"
     "        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)"),
    ("        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)\n"
     "        right.pack_start(self._appearance_card(), False, False, 0)\n"
     "        right.set_size_request(330, -1)",
     "        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)\n"
     "        right.pack_start(self._appearance_card(), False, False, 0)\n"
     "        right.set_size_request(426, -1)"),
    ("    def _settings_card(self, glyph, title, sub):\n"
     "        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        card.get_style_context().add_class('card')",
     "    def _settings_card(self, glyph, title, sub):\n"
     "        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        card.get_style_context().add_class('card')\n"
     "        card.get_style_context().add_class('settings-card')"),
    # 设置页标题区与概览页一致：margin-bottom 22
    ("        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)\n"
     "        heading.set_margin_bottom(16)",
     "        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)\n"
     "        heading.set_margin_bottom(22)"),
]

CSS_TAIL = """
/* 设置页（设计稿 .settings-card{padding:21px}、.settings-layout{gap:17px}） */
.settings-card { padding: 21px; }
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in GUI_SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:70])
            continue
        s = s.replace(old, new, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    c = io.open(CSS, encoding='utf-8').read()
    if '.settings-card { padding: 21px; }' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('patched %d/%d; missing: %s' % (len(GUI_SUBS) - len(missing), len(GUI_SUBS),
                                         missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
