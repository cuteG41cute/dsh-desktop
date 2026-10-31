"""Patch 18: 日志卡内部按设计稿收口。

设计稿：.log-header 45（含 1px 底边框）、.log-body{padding:7px 18px 9px}、
        .log-line{min-height:27px}、行间无额外间距。
GTK 原来：log_body spacing=6 + margin_top=8（多 20px），且没有 .log-body 的类名，
         所以设计稿的内边距根本没生效。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

GUI_SUBS = [
    ("        self.log_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)",
     "        self.log_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        self.log_body.get_style_context().add_class('log-body')"),
]

CSS_TAIL = """
/* 日志正文区（设计稿 .log-body：padding 7px 18px 9px） */
.log-body { padding: 7px 18px 9px; }
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
    if '.log-body { padding: 7px 18px 9px; }' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
