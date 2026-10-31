"""徽标内边距（手搭的 EventBox 不会走 CHIP_PAD）+ 侧栏链接高度补回 2px。

实测：
  badge     37×14  → 设计稿 57×22（dot 5 + gap 5 + 文字 27 + 内边距 18 + 边框 2）
  side-link 196×38 → 设计稿 196×40（去掉 1px 边框后少了 2px）
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

GUI_SUBS = [
    ("        badge_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)",
     "        badge_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)\n"
     "        # EventBox 的 CSS padding 不算尺寸，内边距只能落在子控件的 margin 上\n"
     "        badge_inner.set_margin_top(4)\n"
     "        badge_inner.set_margin_bottom(4)\n"
     "        badge_inner.set_margin_start(9)\n"
     "        badge_inner.set_margin_end(9)"),
]

CSS_SUBS = [
    (".side-link { min-height: 38px; padding: 0 11px; font-size: 11.5px; }",
     ".side-link { min-height: 40px; padding: 0 11px; font-size: 11.5px; }"),
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

    c = io.open(CSS, encoding='utf-8').read()
    for old, new in CSS_SUBS:
        if old in c:
            c = c.replace(old, new, 1)
    io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
