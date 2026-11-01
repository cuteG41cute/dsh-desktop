"""窗口按钮的图标改用 set_from_pixbuf 刷新，不再替换子控件。

现象：三个按钮里"最大化"那个是空的（截图里 — 和 ✕ 都在，中间什么都没有；
更早一次还闪过一个蓝色方块——那是 GTK 在图标缺失时画的 placeholder）。

原因：`_sync_max_icon` 用 remove + add 换图标，而它挂在 window-state-event 的
connect_after 上，启动时的状态事件会把它跑一遍、把刚加上的图标又拆掉。
改成：按钮里放一个固定的 Gtk.Image，切换时只 `set_from_pixbuf`；
并把三个按钮的图标统一由 `_refresh_window_icons()` 按主题色重画。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

OLD_BTN = '''    def _window_button(self, icon, tooltip, handler):
        btn = Gtk.Button()
        btn.get_style_context().add_class('window-btn')
        btn.set_size_request(32, 32)
        btn.set_valign(Gtk.Align.CENTER)
        btn.add(self._icon(icon, 'muted', 14))
        btn.set_tooltip_text(tooltip)
        btn.connect('clicked', lambda *a: handler())
        btn.set_relief(Gtk.ReliefStyle.NONE)
        return btn
'''

NEW_BTN = '''    def _window_button(self, icon, tooltip, handler):
        btn = Gtk.Button()
        btn.get_style_context().add_class('window-btn')
        btn.set_size_request(32, 32)
        btn.set_valign(Gtk.Align.CENTER)
        img = Gtk.Image()
        btn.add(img)
        btn._img = img
        btn._icon_name = icon
        btn.set_tooltip_text(tooltip)
        btn.connect('clicked', lambda *a: handler())
        btn.set_relief(Gtk.ReliefStyle.NONE)
        return btn

    def _refresh_window_icons(self):
        """按当前主题色重画三个窗口图标（最小化/最大化-还原/关闭）。"""
        theme, mode = self._theme_state()
        color = token_color(theme, mode, 'muted')
        for btn in (getattr(self, 'btn_win_min', None),
                    getattr(self, 'btn_win_max', None),
                    getattr(self, 'btn_win_close', None)):
            if btn is None:
                continue
            img = getattr(btn, '_img', None)
            if img is None:
                continue
            pb = icon_pixbuf(getattr(btn, '_icon_name', 'x'), color, 16)
            if pb is not None:
                img.set_from_pixbuf(pb)
'''

OLD_SYNC = '''    def _sync_max_icon(self):
        """最大化后把"最大化"图标换成"还原"。"""
        btn = getattr(self, 'btn_win_max', None)
        if btn is None:
            return
        name = 'restore' if self.is_maximized() else 'maximize'
        child = btn.get_child()
        if isinstance(child, Gtk.Image):
            btn.remove(child)
            btn.add(self._icon(name, 'muted', 14))
        btn.set_tooltip_text('还原' if self.is_maximized() else '最大化')
'''

NEW_SYNC = '''    def _sync_max_icon(self):
        """最大化后把"最大化"图标换成"还原"（只换 pixbuf，不动子控件）。"""
        btn = getattr(self, 'btn_win_max', None)
        if btn is None:
            return
        btn._icon_name = 'restore' if self.is_maximized() else 'maximize'
        btn.set_tooltip_text('还原' if self.is_maximized() else '最大化')
        theme, mode = self._theme_state()
        pb = icon_pixbuf(btn._icon_name, token_color(theme, mode, 'muted'), 16)
        if pb is not None and getattr(btn, '_img', None) is not None:
            btn._img.set_from_pixbuf(pb)
'''

# _recolor_icons 里顺带刷新窗口图标
RECOLOR_OLD = '''            if pb is not None:
                try:
                    img.set_from_pixbuf(pb)
                except Exception:
                    pass
'''
RECOLOR_NEW = '''            if pb is not None:
                try:
                    img.set_from_pixbuf(pb)
                except Exception:
                    pass
        try:
            self._sync_max_icon()          # 最大化/还原图标跟着主题色重画
        except Exception:
            pass
'''


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in ((OLD_BTN, NEW_BTN), (OLD_SYNC, NEW_SYNC), (RECOLOR_OLD, RECOLOR_NEW)):
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0 if not missing else 1


if __name__ == '__main__':
    raise SystemExit(main())
