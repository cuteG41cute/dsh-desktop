"""无边框窗口：自绘窗口按钮 + 拖动 + 双击最大化 + 圆角裁切。

用户要的是"无边框 + 重绘窗口按钮"，即 C 方案：
  self.set_decorated(False) 之后 KWin 不再画标题栏，
  窗口按钮（最小化/最大化/关闭）由我们自己画在顶栏右端，
  顶栏空白处可拖动、双击最大化；
  同时开 RGBA + 自绘圆角裁切，让窗口四角真的是圆的（否则方角会露在桌面上）。

实现要点（都写在注释里）：
  · GtkWindow 的 `draw` 用户处理器在默认处理器（画背景/子控件）之前运行，
    所以在那里清成透明 + 设置圆角裁切，后续绘制就都被裁进去了；
  · 需要 RGBA visual + set_app_paintable；拿不到（或合成器不支持）就退回不裁切；
  · 没有 python3-cairo 时同样跳过裁切，不影响功能。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

# 1) 顶部加 cairo 的可选导入
IMPORT_OLD = "from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402"
IMPORT_NEW = ("from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402\n"
              "\n"
              "try:                      # 圆角裁切需要 cairo；没有就退回方形窗口\n"
              "    import cairo\n"
              "except ImportError:       # pragma: no cover\n"
              "    cairo = None")

# 2) _build 里：换成无边框 + 注册绘制/状态/拖动
BUILD_OLD = ("        self.set_titlebar(None)          # 设计稿没有系统标题栏样式，用自绘顶栏\n"
             "        self.get_style_context().add_class('dsh-window')")
BUILD_NEW = ("        self.set_titlebar(None)\n"
             "        self.get_style_context().add_class('dsh-window')\n"
             "        self._setup_frameless()")

FRAMELESS = '''
    # ------------------------------------------------------------ 无边框窗口
    def _setup_frameless(self):
        """关掉系统标题栏，改用自绘窗口按钮 + 圆角裁切（可用环境变量退回系统标题栏）。"""
        self._frameless = os.environ.get('DSH_MANAGER_SYSTEM_TITLEBAR') != '1'
        self._maximized = False
        self._rgba = False
        if not self._frameless:
            self.set_decorated(True)
            return
        self.set_decorated(False)
        try:
            screen = Gdk.Screen.get_default()
            visual = screen.get_rgba_visual() if screen is not None else None
            if visual is not None and screen.is_composited():
                self.set_visual(visual)
                self.set_app_paintable(True)
                self._rgba = True
        except Exception:
            self._rgba = False
        if self._rgba and cairo is not None:
            self.connect('draw', self._on_window_draw)
        self.connect('window-state-event', self._on_window_state)

    def _corner_radius(self):
        """窗口圆角：跟主题的 app-radius；最大化时为 0。"""
        if self._maximized:
            return 0
        try:
            theme, mode = self._theme_state()
            value = str(token_color(theme, mode, 'app-radius') or '26px')
            return int(round(float(value.replace('px', ''))))
        except Exception:
            return 26

    @staticmethod
    def _rounded_path(cr, x, y, width, height, radius):
        if radius <= 0:
            cr.rectangle(x, y, width, height)
            return
        cr.new_sub_path()
        cr.arc(x + width - radius, y + radius, radius, -1.5708, 0)
        cr.arc(x + width - radius, y + height - radius, radius, 0, 1.5708)
        cr.arc(x + radius, y + height - radius, radius, 1.5708, 3.1416)
        cr.arc(x + radius, y + radius, radius, 3.1416, 4.7124)
        cr.close_path()

    def _on_window_draw(self, _widget, cr):
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

    def _on_window_state(self, _widget, event):
        maximized = bool(event.changed_mask & Gdk.WindowState.MAXIMIZED) and \\
            bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)
        self._maximized = maximized
        shell = getattr(self, 'shell_box', None)
        if shell is not None:
            ctx = shell.get_style_context()
            if maximized:
                ctx.add_class('maximized')
            else:
                ctx.remove_class('maximized')
        self.queue_draw()
        return False

    def _start_window_drag(self, widget, event):
        """顶栏空白处拖动窗口；双击切最大化。按钮等子控件会自己吃掉事件。"""
        if not getattr(self, '_frameless', False):
            return False
        if event.button != 1:
            return False
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self._toggle_maximize()
            return True
        try:
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            return True
        except Exception:
            return False

    def _toggle_maximize(self):
        if self.is_maximized():
            self.unmaximize()
        else:
            self.maximize()

    def _window_buttons(self):
        """右上角三个自绘窗口按钮（最小化 / 最大化-还原 / 关闭）。"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        box.get_style_context().add_class('window-buttons')
        box.set_valign(Gtk.Align.CENTER)
        self.btn_win_min = self._window_button('minus', '最小化', self.iconify)
        self.btn_win_max = self._window_button('maximize', '最大化', self._toggle_maximize)
        self.btn_win_close = self._window_button('x', '关闭', self.close)
        self.btn_win_close.get_style_context().add_class('window-close')
        box.pack_start(self.btn_win_min, False, False, 0)
        box.pack_start(self.btn_win_max, False, False, 0)
        box.pack_start(self.btn_win_close, False, False, 0)
        return box

    def _window_button(self, icon, tooltip, handler):
        btn = Gtk.Button()
        btn.get_style_context().add_class('window-btn')
        btn.set_size_request(32, 32)
        btn.set_valign(Gtk.Align.CENTER)
        btn.add(self._icon(icon, 'muted', 14))
        btn.set_tooltip_text(tooltip)
        btn.connect('clicked', lambda *a: handler())
        btn.set_relief(Gtk.ReliefStyle.NONE)
        return btn

    def _sync_max_icon(self):
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

# 3) 顶栏右端追加窗口按钮（信息按钮之后）
TOP_OLD = "        right.pack_start(info, False, False, 0)\n        bar.pack_end(right, False, False, 0)"
TOP_NEW = ("        right.pack_start(info, False, False, 0)\n"
           "        if getattr(self, '_frameless', False):\n"
           "            sep2 = Gtk.Box()\n"
           "            sep2.get_style_context().add_class('top-divider')\n"
           "            sep2.set_size_request(1, 20)\n"
           "            sep2.set_valign(Gtk.Align.CENTER)\n"
           "            right.pack_start(sep2, False, False, 0)\n"
           "            right.pack_start(self._window_buttons(), False, False, 0)\n"
           "        bar.pack_end(right, False, False, 0)\n"
           "        bar.connect('button-press-event', self._start_window_drag)\n"
           "        bar.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)\n"
           "        self.connect_after('window-state-event',\n"
           "                           lambda *a: (self._sync_max_icon(), False)[1])")

CSS_TAIL = """
/* ==========================================================================
 * 无边框窗口（自绘窗口按钮）
 * ========================================================================== */
.window-btn {
  min-width: 32px;
  min-height: 32px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background-color: transparent;
  background-image: none;
  box-shadow: none;
}
.window-btn:hover { background-color: $(hover); }
.window-close:hover { background-color: alpha($(danger), .16); }
.window-close:hover image { color: $(danger); }
.window-buttons { margin-left: 2px; }

/* 最大化时窗口圆角与外壳圆角都要归零（否则四角会露出桌面） */
.maximized, .maximized.dsh-shell { border-radius: 0; }
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in ((IMPORT_OLD, IMPORT_NEW), (BUILD_OLD, BUILD_NEW), (TOP_OLD, TOP_NEW)):
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)

    if 'def _setup_frameless' not in s:
        anchor = '    def _build(self):'
        if anchor in s:
            s = s.replace(anchor, FRAMELESS + '\n' + anchor, 1)
        else:
            missing.append('anchor _build')
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'
    c = io.open(CSS, encoding='utf-8').read()
    if '.window-btn' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0 if not missing else 1


if __name__ == '__main__':
    raise SystemExit(main())
