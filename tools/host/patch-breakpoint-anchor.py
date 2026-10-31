"""断点判定改挂在 `.dsh-shell` 上，而不是 Gtk.Window。

原因：窗口在真实屏幕上只有 1220 宽（1280×720 屏），断点因此在窗口上算成 narrow；
但离屏截图时内容被搬进 1392 宽的 OffscreenWindow，窗口层不再重算，
于是 1392 的图里套着窄屏布局（实测：参考图与实拍图错位，MAE 3.81→5.24）。

壳（.dsh-shell）才是"应用表面"：它跟着内容一起进离屏窗口，
用它的分配尺寸判定断点、把 narrow/short 类加在它身上，后代选择器才对。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    ("        shell.pack_start(self._build_sidebar(), False, False, 0)\n"
     "        shell.pack_start(self._build_main(), True, True, 0)",
     "        self.shell_box = shell        # 断点判定与 CSS 类都挂在这里\n"
     "        shell.pack_start(self._build_sidebar(), False, False, 0)\n"
     "        shell.pack_start(self._build_main(), True, True, 0)"),
    ("        width = self.get_allocated_width()\n"
     "        height = self.get_allocated_height()\n"
     "        if width <= 1 or height <= 1:\n"
     "            return",
     "        shell = getattr(self, 'shell_box', None)\n"
     "        width = shell.get_allocated_width() if shell is not None else 0\n"
     "        height = shell.get_allocated_height() if shell is not None else 0\n"
     "        if width <= 1 or height <= 1:            # 还没完成布局，用窗口尺寸兜底\n"
     "            width = self.get_allocated_width()\n"
     "            height = self.get_allocated_height()\n"
     "        if width <= 1 or height <= 1:\n"
     "            return"),
    ("        ctx = self.get_style_context()\n"
     "        for cls, on in (('narrow', narrow), ('short', short)):",
     "        ctx = (shell or self).get_style_context()\n"
     "        for cls, on in (('narrow', narrow), ('short', short)):"),
    ("        self.connect('size-allocate', self._on_size_allocate)",
     "        self.shell_box.connect('size-allocate', self._on_size_allocate)\n"
     "        self.connect('size-allocate', self._on_size_allocate)"),
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
