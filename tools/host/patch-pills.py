"""按用户截图修 4 处：

1. **药丸内边距没生效**——实测（tools/host/vm-probe-padding.py）：Gtk.EventBox 的 CSS
   `padding` **不参与尺寸计算**（有无 padding 的 allocation 完全一样 400×20），
   所以 `badge`/`subtle-tag`/`count-pill`/`log-count`/`version-pill` 全都只包住文字。
   改法：把内边距做成内部 label 的 **margin**（margin 会算进子控件尺寸）。
2. **侧栏三个链接有灰边框**——`.side-link` 只清了 background，没清 `border`。
3. **「运行中」「本地实例」胶囊与文字不协调**——状态徽标按设计稿改成"5px 圆点 + 文字"，
   宽度自然撑开；subtle-tag 也补上正确内边距。
4. **常用功能要一排四个**——上一版按 §2.5 在窄屏改成两列，用户要求始终四列。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

GUI_SUBS = [
    # ① _chip：按类名自动加内边距（用 label 的 margin，EventBox 的 padding 无效）
    ("    def _chip(self, text='', *classes, **kwargs):",
     "    # GTK3 的 EventBox 不把 CSS padding 算进尺寸（实测 allocation 完全一样），\n"
     "    # 所以药丸的内边距必须做成内部 label 的 margin。数值取自 DESIGN_SPEC。\n"
     "    CHIP_PAD = {\n"
     "        'badge': (4, 9), 'subtle-tag': (3, 7), 'count-pill': (1, 6),\n"
     "        'log-count': (1, 6), 'version-pill': (3, 7), 'live-text': (0, 0),\n"
     "    }\n\n"
     "    def _chip(self, text='', *classes, **kwargs):"),
    ("        box.image = img\n        box.label = lbl",
     "        box.image = img\n        box.label = lbl\n"
     "        pad = None\n"
     "        for cls in classes:\n"
     "            if cls in self.CHIP_PAD:\n"
     "                pad = self.CHIP_PAD[cls]\n"
     "                break\n"
     "        if pad and not kwargs.get('width'):\n"
     "            lbl.set_margin_top(pad[0])\n"
     "            lbl.set_margin_bottom(pad[0])\n"
     "            lbl.set_margin_start(pad[1])\n"
     "            lbl.set_margin_end(pad[1])"),
    # ② 状态徽标：5px 圆点 + 文字（设计稿 .status-badge）
    ("        self.chip_badge = self._chip('—', 'badge', valign=Gtk.Align.CENTER)",
     "        # 设计稿 .status-badge = 5px 圆点 + 5px 间距 + 文字；圆点颜色随 running/stopped\n"
     "        badge = Gtk.EventBox()\n"
     "        badge.set_visible_window(True)\n"
     "        badge.get_style_context().add_class('badge')\n"
     "        badge.set_valign(Gtk.Align.CENTER)\n"
     "        badge_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)\n"
     "        badge_inner.pack_start(self._chip('', 'badge-dot', width=5, height=5,\n"
     "                                          valign=Gtk.Align.CENTER), False, False, 0)\n"
     "        self.lbl_badge = self._label('—', 'badge-text')\n"
     "        badge_inner.pack_start(self.lbl_badge, False, False, 0)\n"
     "        badge.add(badge_inner)\n"
     "        badge.label = self.lbl_badge\n"
     "        self.chip_badge = badge"),
    # ③ 快捷功能：始终四列（用户明确要求一排四个）
    ("        # ② 快捷功能 2 列 / 4 列\n        self._rebuild_quick_grid(2 if narrow else 4)",
     "        # ② 快捷功能固定四列（用户要求一排四个；设计稿 §2.5 的窄屏两列不再采用）\n"
     "        self._rebuild_quick_grid(4)"),
]

CSS_TAIL = """
/* 侧栏链接：设计稿 .side-link 是无边框的透明按钮（GTK 默认按钮会画 1px 边框） */
.side-link { border: 0; border-image: none; box-shadow: none; background-image: none; }
.side-link.selected, .side-link:selected { border: 0; }

/* 状态徽标里的圆点：颜色随徽标状态（设计稿 .status-badge i{background:currentColor}） */
.badge-dot { background-color: $(muted); border-radius: 3px; }
.badge.running .badge-dot { background-color: $(success); }
.badge.needs-repair .badge-dot { background-color: $(danger); }
.badge-text { font-size: 9px; font-weight: 600; }
.badge.running .badge-text { color: $(success); }
.badge.needs-repair .badge-text { color: $(danger); }
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
    if '侧栏链接：设计稿 .side-link' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('gui patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
