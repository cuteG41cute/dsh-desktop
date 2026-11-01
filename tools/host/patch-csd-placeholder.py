"""KDE Wayland 上 `set_decorated(False)` 还不够——KWin 仍会画服务端标题栏。

实测（tools/host/vm-probe-window.py）：GdkWaylandDisplay、decorated=False、titlebar=None，
但截图里仍有一条带图标和标题的系统标题栏。

原因：GTK3 的 Wayland 后端在"完全没有标题栏"时会退回服务端装饰（KWin 画）。
要让 KWin 不画，必须让窗口走 **CSD**：给 `set_titlebar()` 一个**零高度**的自绘控件。
这样 xdg-decoration 协商成 client-side，KWin 就不再画标题栏，而 0 高度不占地方。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

OLD = """        self.set_decorated(False)
        try:"""
NEW = """        self.set_decorated(False)
        # 关键：给一个零高度的自绘标题栏，让 Wayland 协商成 CSD；
        # 否则 GTK 会退回服务端装饰，KWin 照样画标题栏。
        placeholder = Gtk.Box()
        placeholder.set_size_request(-1, 0)
        self.set_titlebar(placeholder)
        try:"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    if 'placeholder = Gtk.Box()' in s:
        print('already patched')
        return 0
    if OLD not in s:
        raise SystemExit('FAIL: 找不到 set_decorated(False) 后那段')
    s = s.replace(OLD, NEW, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('zero-height CSD placeholder added')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
