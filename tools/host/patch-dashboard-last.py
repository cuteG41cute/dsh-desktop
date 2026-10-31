"""Patch 17: 收掉概览页最后两项可测偏差（metric-row 高度、eyebrow 盒子宽度）。

metric-row：设计稿高 45（padding-top 13 + 内容 32），GTK 只算出 34 → 给一个 min-height。
eyebrow：设计稿里它是行内元素（宽 285.7），GTK 的 label 默认撑满整行（919）——
         文字位置一致，但盒子宽度差 633。设置 halign=START 让盒子贴合文字。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

GUI_SUBS = [
    # 两个页面上的 eyebrow 都贴合文字宽度
    ("        text.pack_start(self._label('INSTANCE OVERVIEW', 'eyebrow'), False, False, 0)",
     "        _eyebrow = self._label('INSTANCE OVERVIEW', 'eyebrow')\n"
     "        _eyebrow.set_halign(Gtk.Align.START)\n"
     "        text.pack_start(_eyebrow, False, False, 0)"),
    ("        text.pack_start(self._label('MANAGER PREFERENCES', 'eyebrow'), False, False, 0)",
     "        _eyebrow2 = self._label('MANAGER PREFERENCES', 'eyebrow')\n"
     "        _eyebrow2.set_halign(Gtk.Align.START)\n"
     "        text.pack_start(_eyebrow2, False, False, 0)"),
]

CSS_TAIL = """
/* 指标行：设计稿 .metric-row 高 45（padding-top 13 + 内容 32） */
.metric-row { min-height: 44px; }
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
    if '.metric-row { min-height: 44px; }' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
