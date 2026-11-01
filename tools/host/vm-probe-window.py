#!/usr/bin/env python3
"""跑真窗口，把窗口属性打到日志里（判断 set_decorated 到底生效没有）。"""
import os
import sys
import time

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
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from vm_fixture import FakeManager  # noqa: E402


def main():
    from dsh_manager import gui as g

    win = g.ManagerWindow(manager=FakeManager())
    win.show_all()

    def report():
        try:
            display = Gdk.Display.get_default()
            screen = Gdk.Screen.get_default()
            print('backend      :', type(display).__name__)
            print('frameless    :', getattr(win, '_frameless', None))
            print('decorated    :', win.get_decorated())
            print('titlebar     :', win.get_titlebar())
            print('rgba window  :', getattr(win, '_rgba', None))
            print('composited   :', screen.is_composited() if screen else None)
            print('rgba visual  :', screen.get_rgba_visual() is not None if screen else None)
            print('corner radius:', win._corner_radius())
            print('buttons      :', [b.get_tooltip_text() for b in
                                      (getattr(win, 'btn_win_min', None),
                                       getattr(win, 'btn_win_max', None),
                                       getattr(win, 'btn_win_close', None)) if b is not None])
        except Exception as exc:
            print('report failed:', exc)
        sys.stdout.flush()
        GLib.timeout_add(6000, lambda: (Gtk.main_quit(), False)[1])
        return False

    GLib.timeout_add(1500, report)
    Gtk.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
