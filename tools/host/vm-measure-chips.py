#!/usr/bin/env python3
"""按类名量控件尺寸（不限白名单），用来对设计稿的 57×22 这类数字。

  vm-measure-chips.py 1220x760 count-pill badge subtle-tag side-link
"""
import os
import sys

RUNTIME = "/run/user/%d" % os.getuid()
os.environ.setdefault("XDG_RUNTIME_DIR", RUNTIME)
os.environ.setdefault("DISPLAY", ":1")
os.environ.setdefault("GDK_BACKEND", "x11")
os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=%s/bus" % RUNTIME)
for _e in os.listdir(RUNTIME):
    if _e.startswith("xauth_"):
        os.environ.setdefault("XAUTHORITY", os.path.join(RUNTIME, _e))
sys.path.insert(0, os.path.expanduser("~/dsh-dev"))
sys.path.insert(0, "/tmp/dsh-vm")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk  # noqa: E402

from vm_fixture import DESIGN, FakeManager, inject_logs, pump  # noqa: E402


def walk(widget, out):
    try:
        classes = list(widget.get_style_context().list_classes() or [])
    except Exception:
        classes = []
    if classes and widget.get_visible():
        a = widget.get_allocation()
        out.append((classes, a.width, a.height, widget.get_name(),
                    widget.get_text() if isinstance(widget, Gtk.Label) else ''))
    if isinstance(widget, Gtk.Container):
        for ch in widget.get_children():
            walk(ch, out)


def main():
    size = sys.argv[1] if len(sys.argv) > 1 else '1220x760'
    targets = sys.argv[2:] or ['count-pill', 'badge', 'subtle-tag', 'side-link']
    width, height = (int(v) for v in size.split('x'))
    from dsh_manager import gui as g

    win = g.ManagerWindow(manager=FakeManager())
    win.set_default_size(width, height)
    win.show_all()
    pump(600)
    win.selected = win.manager.instance_at(DESIGN["selected"])
    win.refresh()
    pump(300)
    inject_logs(win)
    pump(300)
    child = win.get_child()
    win.remove(child)
    off = Gtk.OffscreenWindow()
    off.get_style_context().add_class('dsh-window')
    off.set_size_request(width, height)
    off.add(child)
    off.show_all()
    off.resize(width, height)
    child.set_size_request(width, height)
    pump(700)

    recs = []
    walk(off, recs)
    for target in targets:
        hits = [r for r in recs if target in r[0]]
        print('%s: %d 个' % (target, len(hits)))
        for classes, w, h, name, text in hits[:4]:
            print('   %-30s %4dx%-4d %s %s' % (','.join(classes)[:30], w, h, name,
                                               ('"%s"' % text[:10]) if text else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
