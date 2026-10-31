"""修用户截图里指出的 5 处观感问题（都是 GTK 布局细节，不是配色）。

1. 状态点/圆点被拉成"竖长条"：`_chip('', 'status-dot', width=6, height=6)` 里塞了一个
   空 Gtk.Label（自然高约 17），size_request 只是最小值 → 盒子变成 6×17。
   纯色块不该有子控件。
2. `我的实例 2` 的计数胶囊同样被拉高（没有 valign 时 EventBox 会填满父容器高度）。
   → `_chip` 默认 valign=CENTER。
3. 侧栏「+」按钮画出了白色卡片底/边框：`.icon-btn` 没把 GTK 默认按钮底清掉。
4. 「● 服务正常」用了文字圆点（黑色大圆），设计稿是 5px 成功色圆点 + 成功色文字。
5. 「更多」按钮用 '⋯' 字形渲染，比设计稿的 i-more 图标大一号。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    # ① 纯色块不加子控件
    ("        box = Gtk.EventBox()\n"
     "        box.set_visible_window(True)\n"
     "        for cls in classes:\n"
     "            box.get_style_context().add_class(cls)\n"
     "        if kwargs.get('icon'):",
     "        box = Gtk.EventBox()\n"
     "        box.set_visible_window(True)\n"
     "        for cls in classes:\n"
     "            box.get_style_context().add_class(cls)\n"
     "        width = kwargs.get('width')\n"
     "        height = kwargs.get('height')\n"
     "        if not text and width and height and not kwargs.get('icon'):\n"
     "            # 纯色块（状态点/圆点）：不能塞空 label —— 它的自然高度会把盒子撑成竖条\n"
     "            lbl = Gtk.Label(label='')\n"
     "            lbl.set_visible(False)\n"
     "            box.label = lbl\n"
     "            box.image = None\n"
     "            box.set_size_request(width, height)\n"
     "            box.set_valign(kwargs.get('valign') or Gtk.Align.CENTER)\n"
     "            if kwargs.get('hexpand'):\n"
     "                box.set_hexpand(True)\n"
     "            return box\n"
     "        if kwargs.get('icon'):"),
    # ② _chip 默认垂直居中（不再让胶囊被拉高）
    ("        width = kwargs.get('width')\n"
     "        height = kwargs.get('height')\n"
     "        if width and height:\n"
     "            box.set_size_request(width, height)\n"
     "        if kwargs.get('valign') is not None:\n"
     "            box.set_valign(kwargs['valign'])",
     "        if width and height:\n"
     "            box.set_size_request(width, height)\n"
     "        # 不指定时默认居中：否则 EventBox 会填满父容器高度（计数胶囊被拉成竖条）\n"
     "        box.set_valign(kwargs.get('valign') or Gtk.Align.CENTER)"),
    # ③ 「● 服务正常」→ 5px 成功色圆点 + 文字
    ("        self.chip_live = self._chip('● 服务正常', 'live-indicator', valign=Gtk.Align.CENTER)",
     "        live = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)\n"
     "        live.get_style_context().add_class('live-indicator')\n"
     "        live.pack_start(self._chip('', 'live-dot', width=5, height=5,\n"
     "                                   valign=Gtk.Align.CENTER), False, False, 0)\n"
     "        self.lbl_live = self._label('服务正常', 'live-text')\n"
     "        live.pack_start(self.lbl_live, False, False, 0)\n"
     "        self.chip_live = live"),
    # ④ 「更多」用图标
    ("        more = Gtk.MenuButton()\n"
     "        more.get_style_context().add_class('btn')",
     "        more = Gtk.MenuButton()\n"
     "        more.set_valign(Gtk.Align.CENTER)\n"
     "        more.get_style_context().add_class('btn')"),
]

# chip_live 的文字更新改成 lbl_live
LIVE_OLD = "        self.chip_live.label.set_text('● 服务正常' if running else '● 未运行')"
LIVE_NEW = ("        self.lbl_live.set_text('服务正常' if running else '未运行')\n"
            "        ctx = self.lbl_live.get_style_context()\n"
            "        if running:\n"
            "            ctx.remove_class('live-stopped')\n"
            "        else:\n"
            "            ctx.add_class('live-stopped')")

CSS_TAIL = """
/* 图标按钮：设计稿 .icon-btn{background:transparent;border:0}——
   GTK 默认主题会给按钮画底色/边框，必须显式清掉 */
.icon-btn, .icon-btn.small {
  background-color: transparent;
  background-image: none;
  border: 0;
  box-shadow: none;
  padding: 0;
}
.icon-btn:hover { background-color: $(hover); }

/* 运行指示：5px 成功色圆点 + 成功色文字（设计稿 .live-indicator） */
.live-indicator { color: $(success); }
.live-dot { background-color: $(success); border-radius: 3px; }
.live-text { color: $(success); font-size: 8.5px; }
.live-text.live-stopped, .live-indicator.live-stopped { color: $(muted); }
.live-dot.live-stopped { background-color: $(muted); }

/* 计数胶囊：设计稿 .count-pill{padding:1px 6px;border-radius:10px} */
.count-pill { padding: 1px 6px; border-radius: 10px; min-height: 12px; font-size: 10px; }
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    if LIVE_OLD in s:
        s = s.replace(LIVE_OLD, LIVE_NEW, 1)
    else:
        missing.append('live label update')
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'
    c = io.open(CSS, encoding='utf-8').read()
    if '图标按钮：设计稿 .icon-btn' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('gui patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
