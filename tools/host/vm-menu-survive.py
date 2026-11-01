#!/usr/bin/env python3
"""在真实会话里弹一个 GTK 右键菜单，看看它会不会「被刷新掉」。

不依赖鼠标注入：窗口自己 popup 一个菜单，然后我们在外面连拍几帧。
留 12 秒，够外面抓 3 帧。
"""
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402


class Win(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title='MENU-TEST')
        self.set_default_size(420, 260)
        self.set_position(Gtk.WindowPosition.CENTER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.pack_start(Gtk.Label(label='右键菜单存活测试', xalign=0), False, False, 0)
        self.entry = Gtk.Entry()
        self.entry.set_text('SELECT ME')
        box.pack_start(self.entry, False, False, 0)
        self.add(box)
        self.menu = Gtk.Menu()
        for label in ('剪切', '复制', '粘贴', '全选'):
            item = Gtk.MenuItem(label=label)
            item.connect('activate', lambda *a: None)
            self.menu.append(item)
        self.menu.show_all()

    def pop_it(self):
        print('[menu-test] 弹出菜单', flush=True)
        self.menu.popup(None, None, None, None, 0, Gtk.get_current_event_time())
        return False


def main():
    win = Win()
    win.show_all()
    GLib.timeout_add(1500, win.pop_it)
    GLib.timeout_add_seconds(12, Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
