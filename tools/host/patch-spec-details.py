"""按 DESIGN_SPEC 补齐几处细节 + 窄屏侧栏内边距。

- §2.5 窄屏 `.sidebar{padding-left/right:12px}`（我漏了；220 宽 + 16 内边距导致实例名被截）
- §7.16 Toast 底边 35px（原 26）
- §7.12 日志行字段间距 11px（原 10）
- §7.2 实例行状态点 6px（原 7）
- §7.14 「更多」菜单宽 215px
"""
import io

import re

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

GUI_SUBS = [
    # Toast 底边 26 → 35
    ("        self.toast_revealer.set_margin_bottom(26)",
     "        self.toast_revealer.set_margin_bottom(35)   # 设计稿 .toast{bottom:35px}"),
    # 实例行状态点 7 → 6
    ("        dot = self._chip('', 'status-dot', width=7, height=7, valign=Gtk.Align.CENTER)",
     "        dot = self._chip('', 'status-dot', width=6, height=6, valign=Gtk.Align.CENTER)"),
    # 日志行字段间距 10 → 11
    ("            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)\n"
     "            t = self._label('', 'log-time')",
     "            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)\n"
     "            t = self._label('', 'log-time')"),
]

CSS_TAIL = """
/* 窄屏侧栏内边距（DESIGN_SPEC §2.5：≤1280px 时左右 12px） */
.narrow .sidebar { padding-left: 12px; padding-right: 12px; }
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in GUI_SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)

    # 「更多」菜单宽 215（MenuButton 的 popover 内容没有类名，直接给宽度）
    if 'set_size_request(215, -1)' not in s:
        anchor = "        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)"
        if anchor in s:
            s = s.replace(anchor, anchor + "\n        menu.set_size_request(215, -1)   # 设计稿 .more-menu 宽 215",
                          1)
        else:
            missing.append('more menu anchor')

    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    c = io.open(CSS, encoding='utf-8').read()
    if '窄屏侧栏内边距' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
