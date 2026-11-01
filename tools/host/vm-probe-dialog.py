#!/usr/bin/env python3
"""起主窗口并自动打开插件对话框，方便截图验收对话框风格（跑 18 秒后自己退出）。"""
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

from vm_fixture import DESIGN, FakeManager  # noqa: E402


def main():
    from dsh_manager import gui as g

    win = g.ManagerWindow(manager=FakeManager())
    theme = os.environ.get('DSH_PROBE_THEME', '')
    mode = os.environ.get('DSH_PROBE_MODE', '')
    if theme or mode:
        win.apply_theme(theme or None, mode or None, persist=False)
    win.show_all()

    def open_plugins():
        try:
            win.selected = win.manager.instance_at(DESIGN['selected'])
            win.refresh()
            win.on_plugins()
        except Exception as exc:
            print('open dialog failed:', exc)
        sys.stdout.flush()
        GLib.timeout_add(16000, lambda: (Gtk.main_quit(), False)[1])
        return False

    GLib.timeout_add(2500, open_plugins)
    Gtk.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
