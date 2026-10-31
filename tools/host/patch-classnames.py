"""Patch 13: 给日志卡和指标行挂上设计稿的类名（否则 CSS 规则根本没命中）。"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    ("        log_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        log_card.get_style_context().add_class('card')\n"
     "        log_card.set_margin_top(18)",
     "        log_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        log_card.get_style_context().add_class('card')\n"
     "        log_card.get_style_context().add_class('log-card')   # .log-card{padding:0}\n"
     "        log_card.set_margin_top(20)"),
    ("        metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)\n"
     "        metrics.set_margin_top(13)",
     "        metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)\n"
     "        metrics.get_style_context().add_class('metric-row')\n"
     "        metrics.set_margin_top(13)"),
]


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:70])
            continue
        s = s.replace(old, new, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched %d/%d; missing: %s' % (len(SUBS) - len(missing), len(SUBS),
                                         missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
