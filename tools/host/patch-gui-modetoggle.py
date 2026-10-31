"""Patch 8: 顶栏日夜开关按设计稿做成「太阳 + 月亮 + 滑块」胶囊。

设计稿：.mode-toggle{width:57;height:30;border-radius:16;padding:0;display:flex;
justify-content:space-around} + 两个 14px 图标 + 22px 圆滑块（白天在左、夜间平移 27px）。
GTK3 没有 transform，所以滑块位置用 halign + margin 切两边。
"""
import io

P = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    # 1) 顶部栏：改用自绘胶囊
    ("        self.btn_mode = self._button('', '☀  日间', 'mode-toggle',\n"
     "                                     handler=self.on_toggle_mode)\n"
     "        self.btn_mode.set_valign(Gtk.Align.CENTER)",
     "        self.btn_mode = self._build_mode_toggle()\n"
     "        self.btn_mode.set_valign(Gtk.Align.CENTER)"),
    # 2) 同步标签时改为更新图标/滑块，而不是改文字
    ("        if getattr(self, 'btn_mode', None) is not None:\n"
     "            self.btn_mode.set_label('☾  夜间' if mode == 'night' else '☀  日间')",
     "        self._sync_mode_toggle(mode)"),
]

METHODS = '''
    # ------------------------------------------------------------ 日夜开关
    def _build_mode_toggle(self):
        """设计稿的 .mode-toggle：太阳/月亮两个图标 + 一个圆滑块。"""
        btn = Gtk.Button()
        btn.get_style_context().add_class('mode-toggle')
        btn.connect('clicked', self.on_toggle_mode)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.set_homogeneous(True)
        self.icon_mode_sun = self._icon('sun', 'accent', 14)
        self.icon_mode_moon = self._icon('moon', 'muted', 14)
        row.pack_start(self.icon_mode_sun, True, True, 0)
        row.pack_start(self.icon_mode_moon, True, True, 0)

        thumb = Gtk.EventBox()
        thumb.set_visible_window(True)
        thumb.get_style_context().add_class('mode-thumb')
        thumb.set_size_request(22, 22)
        thumb.set_valign(Gtk.Align.CENTER)
        thumb.set_halign(Gtk.Align.START)
        thumb.set_margin_start(3)
        self.chip_mode_thumb = thumb

        overlay = Gtk.Overlay()
        overlay.add(row)
        overlay.add_overlay(thumb)
        btn.add(overlay)
        return btn

    def _sync_mode_toggle(self, mode):
        """滑块靠 halign+margin 换边（GTK3 没有 transform:translateX）。"""
        thumb = getattr(self, 'chip_mode_thumb', None)
        if thumb is not None:
            if mode == 'night':
                thumb.set_halign(Gtk.Align.END)
                thumb.set_margin_start(0)
                thumb.set_margin_end(3)
            else:
                thumb.set_halign(Gtk.Align.START)
                thumb.set_margin_end(0)
                thumb.set_margin_start(3)
        sun = getattr(self, 'icon_mode_sun', None)
        moon = getattr(self, 'icon_mode_moon', None)
        if sun is not None:
            sun.set_opacity(0.5 if mode == 'night' else 1.0)
        if moon is not None:
            moon.set_opacity(1.0 if mode == 'night' else 0.55)
'''

TAIL_CSS = """
/* 日夜开关的滑块与图标（设计稿 .mode-thumb / .moon-icon） */
.mode-thumb { background-color: $(hover); border-radius: 11px; }
.mode-toggle button, .mode-toggle { padding: 0; }
"""


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:70])
            continue
        s = s.replace(old, new, 1)

    if 'def _build_mode_toggle' not in s:
        anchor = '    def _build_dashboard(self):'
        if anchor in s:
            s = s.replace(anchor, METHODS + '\n' + anchor, 1)
        else:
            missing.append('anchor _build_dashboard')

    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)

    CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'
    c = io.open(CSS, encoding='utf-8').read()
    if 'mode-thumb' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + TAIL_CSS)

    print('patched %d/%d; missing: %s' % (len(SUBS) - len(missing), len(SUBS),
                                         missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
