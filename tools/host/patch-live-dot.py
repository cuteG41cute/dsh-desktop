"""运行指示的圆点要跟着状态变灰（用户截图发现的遗留 bug）。

上一版把「● 服务正常」换成了「色块圆点 + 文字」，但状态更新只改了文字的颜色类，
圆点（独立 EventBox）永远保持成功色 —— 于是"未运行"旁边仍是一个绿点。

修法：把圆点存成 self.chip_live_dot，更新时和文字一起加/去 live-stopped 类。
（设计稿里圆点是 background: currentColor，颜色本来就跟着文字走。）
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    ("        live.pack_start(self._chip('', 'live-dot', width=5, height=5,\n"
     "                                   valign=Gtk.Align.CENTER), False, False, 0)",
     "        self.chip_live_dot = self._chip('', 'live-dot', width=5, height=5,\n"
     "                                        valign=Gtk.Align.CENTER)\n"
     "        live.pack_start(self.chip_live_dot, False, False, 0)"),
    ("        self.lbl_live.set_text('服务正常' if running else '未运行')\n"
     "        ctx = self.lbl_live.get_style_context()\n"
     "        if running:\n"
     "            ctx.remove_class('live-stopped')\n"
     "        else:\n"
     "            ctx.add_class('live-stopped')",
     "        self.lbl_live.set_text('服务正常' if running else '未运行')\n"
     "        # 文字与圆点必须一起换：圆点是独立控件，只改文字会留下一个绿点\n"
     "        for widget in (self.lbl_live, self.chip_live_dot):\n"
     "            ctx = widget.get_style_context()\n"
     "            if running:\n"
     "                ctx.remove_class('live-stopped')\n"
     "            else:\n"
     "                ctx.add_class('live-stopped')"),
]


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0 if not missing else 1


if __name__ == '__main__':
    raise SystemExit(main())
