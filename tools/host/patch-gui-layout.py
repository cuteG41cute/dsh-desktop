"""Patch gui.py layout numbers to match the design (UTF-8 safe, idempotent)."""
import io

P = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    # 快捷控制卡宽度：设计稿 402.25（实例卡 663.73，间距 16，合计 1082）
    ("        control = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        control.get_style_context().add_class('card')\n"
     "        control.set_size_request(310, -1)",
     "        control = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        control.get_style_context().add_class('card')\n"
     "        control.get_style_context().add_class('control-card')\n"
     "        control.set_size_request(402, -1)   # 设计稿 .control-card 402.25"),
    ("        info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        info_card.get_style_context().add_class('card')\n"
     "        info_card.set_hexpand(True)",
     "        info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        info_card.get_style_context().add_class('card')\n"
     "        info_card.get_style_context().add_class('instance-card')\n"
     "        info_card.set_hexpand(True)"),
    # 卡片内部：设计稿 .instance-meta{margin-top:17}、.metric-row{margin-top:18;padding-top:13}
    ("        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=13)\n"
     "        meta.set_margin_top(16)",
     "        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=13)\n"
     "        meta.set_margin_top(17)"),
    ("        sep = Gtk.Separator()\n        sep.set_margin_top(14)",
     "        sep = Gtk.Separator()\n        sep.set_margin_top(18)"),
    ("        metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)\n"
     "        metrics.set_margin_top(12)",
     "        metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)\n"
     "        metrics.set_margin_top(13)"),
    # 快捷功能区图标：垂直居中（否则被拉成 34×82）
    ("        box.pack_start(self._chip(glyph, 'quick-icon', width=34, height=34), False, False, 0)",
     "        box.pack_start(self._chip(glyph, 'quick-icon', width=34, height=34,\n"
     "                                  valign=Gtk.Align.CENTER), False, False, 0)"),
    # 顶栏控件垂直居中 + 尺寸
    ("        self.btn_mode = self._button('', '☀  日间', 'mode-toggle',\n"
     "                                     handler=self.on_toggle_mode)",
     "        self.btn_mode = self._button('', '☀  日间', 'mode-toggle',\n"
     "                                     handler=self.on_toggle_mode)\n"
     "        self.btn_mode.set_valign(Gtk.Align.CENTER)"),
]


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:70])
            continue
        s = s.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched %d/%d; missing: %s' % (len(SUBS) - len(missing), len(SUBS),
                                         missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
