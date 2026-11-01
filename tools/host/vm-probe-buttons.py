#!/usr/bin/env python3
"""打印三个自绘窗口按钮的构成（图标是否加载成功 / 尺寸 / 位置）。"""
import os
import sys

RUNTIME = "/run/user/%d" % os.getuid()
os.environ.setdefault("XDG_RUNTIME_DIR", RUNTIME)
os.environ.setdefault("DISPLAY", ":1")
os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=%s/bus" % RUNTIME)
for _e in os.listdir(RUNTIME):
    if _e.startswith("xauth_"):
        os.environ.setdefault("XAUTHORITY", os.path.join(RUNTIME, _e))
sys.path.insert(0, os.path.expanduser("~/dsh-dev"))
sys.path.insert(0, "/tmp/dsh-vm")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from vm_fixture import FakeManager  # noqa: E402


def main():
    from dsh_manager import gui as g

    # 先直接验证三个 SVG 能否加载
    for name in ('minus', 'maximize', 'restore', 'x'):
        pb = g.icon_pixbuf(name, '#747288', 14)
        print('icon_pixbuf(%-8s) ->' % name, None if pb is None else '%dx%d' % (pb.get_width(), pb.get_height()))

    win = g.ManagerWindow(manager=FakeManager())
    win.show_all()

    def report():
        for label, btn in (('min', win.btn_win_min), ('max', win.btn_win_max), ('close', win.btn_win_close)):
            a = btn.get_allocation()
            child = btn.get_child()
            info = type(child).__name__
            if isinstance(child, Gtk.Image):
                pb = child.get_pixbuf()
                info += ' pixbuf=%s' % (None if pb is None else '%dx%d' % (pb.get_width(), pb.get_height()))
            print('%-6s alloc=(%d,%d %dx%d) child=%s' % (label, a.x, a.y, a.width, a.height, info))
        hid = win.btn_win_max.get_child()
        print('max child storage-type:', hid.get_storage_type() if isinstance(hid, Gtk.Image) else '-')
        sys.stdout.flush()
        GLib.timeout_add(500, lambda: (Gtk.main_quit(), False)[1])
        return False

    GLib.timeout_add(1500, report)
    Gtk.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
