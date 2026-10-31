#!/usr/bin/env python3
"""按类名找控件，打印它的直接子控件与各自分配盒（排查"多出来的 21px"这种inside offset）。"""
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

TARGET = sys.argv[1] if len(sys.argv) > 1 else 'log-card'
WIDTH, HEIGHT = 1392, 852


def find(widget, cls):
    try:
        if cls in (widget.get_style_context().list_classes() or []):
            return widget
    except Exception:
        pass
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            hit = find(child, cls)
            if hit is not None:
                return hit
    return None


def main():
    from dsh_manager import gui as g

    win = g.ManagerWindow(manager=FakeManager())
    win.set_default_size(WIDTH, HEIGHT)
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
    off.set_size_request(WIDTH, HEIGHT)
    off.add(child)
    off.show_all()
    off.resize(WIDTH, HEIGHT)
    child.set_size_request(WIDTH, HEIGHT)
    pump(700)

    card = find(off, TARGET)
    if card is None:
        print('找不到 class=%s' % TARGET)
        return 1
    a = card.get_allocation()
    print('card %s alloc=(%d,%d %dx%d)' % (TARGET, a.x, a.y, a.width, a.height))
    try:
        m = card.get_style_context().get_margin(Gtk.StateFlags.NORMAL)
        p = card.get_style_context().get_padding(Gtk.StateFlags.NORMAL)
        print('  css margin=(t%d r%d b%d l%d) padding=(t%d r%d b%d l%d)'
              % (m.top, m.right, m.bottom, m.left, p.top, p.right, p.bottom, p.left))
    except Exception as exc:
        print('  margin/padding 读取失败:', exc)
    if isinstance(card, Gtk.Container):
        for idx, ch in enumerate(card.get_children()):
            ca = ch.get_allocation()
            try:
                classes = ','.join(ch.get_style_context().list_classes() or [])
            except Exception:
                classes = '?'
            print('  [%d] %-22s classes=%-18s alloc=(%d,%d %dx%d) relative_dy=%d'
                  % (idx, ch.get_name(), classes[:18], ca.x, ca.y, ca.width, ca.height,
                     ca.y - a.y))
    return 0


if __name__ == '__main__':
    sys.exit(main())
