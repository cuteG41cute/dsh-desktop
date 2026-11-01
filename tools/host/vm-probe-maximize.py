#!/usr/bin/env python3
"""最大化状态验收：起窗 → 最大化 → 停留 20s（外部脚本随后截图）。"""
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

    win = g.ManagerWindow(manager=FakeManager())
    win.show_all()

    def do_max():
        win.maximize()
        print('maximized=%s radius=%s' % (win.is_maximized(), win._corner_radius()))
        sys.stdout.flush()
        GLib.timeout_add(18000, lambda: (Gtk.main_quit(), False)[1])
        return False

    GLib.timeout_add(2000, do_max)
    Gtk.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
