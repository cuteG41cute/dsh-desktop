"""无边框窗口要自己画背景。

`set_app_paintable(True)` 之后 GTK 不再替我们填窗口背景：上一版把窗口清成透明后，
CSS 里的窗口背景图没有生效，于是整个窗口半透明、桌面上的终端窗口直接透了过来
（截图里能看到 konsole 的字）。

修法：在 draw 处理器里显式把主题背景图铺满窗口（按窗口尺寸缩放），
圆角裁切之后再画；子控件继续由默认处理器绘制。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

OLD = '''    def _on_window_draw(self, _widget, cr):
        """先清成透明，再按圆角裁切；之后的背景与子控件绘制都落在这个裁切里。"""
        alloc = self.get_allocation()
        cr.save()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        self._rounded_path(cr, 0, 0, alloc.width, alloc.height, self._corner_radius())
        cr.clip()
        cr.restore()
        return False          # 继续默认绘制（背景 + 子控件），它们继承上面的裁切
'''

NEW = '''    def _window_bg_pixbuf(self):
        """当前主题的预渲染背景图（和 CSS 里 $(bg-image) 是同一张）。"""
        theme, mode = self._theme_state()
        key = '%s-%s' % (theme, mode)
        cached = getattr(self, '_bg_cache', None) or {}
        if key in cached:
            return cached[key]
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'backgrounds', '%s.png' % key)
        pb = None
        if os.path.exists(path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(path)
            except Exception:
                pb = None
        cached[key] = pb
        self._bg_cache = cached
        return pb

    def _on_window_draw(self, _widget, cr):
        """清透明（含四角）→ 圆角裁切 → 铺主题背景；子控件由默认处理器接着画。"""
        alloc = self.get_allocation()
        # 1) 整幅清成透明：圆角之外必须真的透出桌面
        cr.save()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.restore()
        # 2) 圆角裁切（这个 clip 要留给子控件，所以不能 restore 掉）
        self._rounded_path(cr, 0, 0, alloc.width, alloc.height, self._corner_radius())
        cr.clip()
        # 3) 自己画窗口背景：app_paintable 之后 GTK 不会替我们填
        pb = self._window_bg_pixbuf()
        if pb is not None and pb.get_width() > 0 and pb.get_height() > 0:
            cr.save()
            cr.scale(alloc.width / float(pb.get_width()),
                     alloc.height / float(pb.get_height()))
            Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
            cr.paint()
            cr.restore()
        return False
'''


def main():
    s = io.open(GUI, encoding='utf-8').read()
    if 'def _window_bg_pixbuf' in s:
        print('already patched')
        return 0
    if OLD not in s:
        raise SystemExit('FAIL: 找不到 _on_window_draw 原文')
    s = s.replace(OLD, NEW, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('window background now painted by us')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
