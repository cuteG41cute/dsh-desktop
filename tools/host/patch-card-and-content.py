"""Patch 11: 卡片高度按"设计稿 height 含 padding"重算，并修正内容区 padding 归属。

实测：`.card` 的 padding 18/20 会让高度 205 变成 241（205 是**内容**最小高度）。
所以 CSS 里 min-height 要写成 205 - padding(36) - border(2) = 167。
同时把 .content 的 25/30/15 从 GTK 的 margin 改成 CSS padding（设计稿是 padding，
这样盒子本身的 x/y/w/h 才能和施工图对上，几何门禁才有意义）。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

GUI_SUBS = [
    ("        control.set_size_request(402, 205)   # 设计稿 .control-card 402.25 x 205",
     "        control.set_size_request(402, -1)   # 高度交给 CSS（205 含 padding）"),
    ("        info_card.set_size_request(-1, 205)   # 设计稿 .instance-card 205",
     ""),
    # 内容区：margin → CSS padding
    ("        page.get_style_context().add_class('content')\n"
     "        # 设计稿 .content{padding:25px 30px 15px}\n"
     "        page.set_margin_top(25)\n"
     "        page.set_margin_bottom(15)\n"
     "        page.set_margin_start(30)\n"
     "        page.set_margin_end(30)",
     "        page.get_style_context().add_class('content')\n"
     "        # 设计稿 .content{padding:25px 30px 15px} —— 用 CSS padding，盒子本身仍是满宽"),
    # 页脚要撑满一行（设计稿 space-between）
    ("        page.pack_start(footer, False, False, 0)",
     "        footer.set_hexpand(True)\n        page.pack_start(footer, False, False, 0)"),
]

CSS_TAIL = """
/* 内容区 padding（设计稿 .content：25px 30px 15px） */
.content { padding: 25px 30px 15px; }
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in GUI_SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:70])
            continue
        s = s.replace(old, new)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    c = io.open(CSS, encoding='utf-8').read()
    if '.content { padding: 25px 30px 15px; }' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('gui patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
