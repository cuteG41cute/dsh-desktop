#!/usr/bin/env python3
"""验证：Gtk.EventBox 上的 CSS padding 是否参与尺寸计算（决定药丸怎么加内边距）。"""
import os
import sys

RUNTIME = "/run/user/%d" % os.getuid()
os.environ.setdefault("XDG_RUNTIME_DIR", RUNTIME)
os.environ.setdefault("DISPLAY", ":1")
os.environ.setdefault("GDK_BACKEND", "x11")
for _e in os.listdir(RUNTIME):
    if _e.startswith("xauth_"):
        os.environ.setdefault("XAUTHORITY", os.path.join(RUNTIME, _e))

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

Gtk.init([])

CSS = b"""
.pad { padding: 3px 9px; background-color: alpha(#7968e8, .1); border-radius: 6px; }
.padlabel label { font-size: 9px; }
"""


def measure(name, box, label_class=None):
    label = Gtk.Label(label='\u8fd0\u884c\u4e2d')
    if label_class:
        label.get_style_context().add_class(label_class)
    box.add(label)
    w, h = box.get_preferred_width()[1], box.get_preferred_height()[1]
    print('%-28s preferred=%dx%d' % (name, w, h))
    return w, h


def main():
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    screen = Gdk.Screen.get_default()
    Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    win = Gtk.Window()
    win.set_default_size(400, 200)
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    win.add(vbox)

    plain = Gtk.EventBox()
    plain.set_visible_window(True)
    vbox.pack_start(plain, False, False, 0)
    measure('EventBox 无样式', plain)

    padded = Gtk.EventBox()
    padded.set_visible_window(True)
    padded.get_style_context().add_class('pad')
    vbox.pack_start(padded, False, False, 0)
    measure('EventBox + .pad(3/9)', padded)

    win.show_all()
    for _ in range(50):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
    for name, box in (('无样式', plain), ('有 padding', padded)):
        a = box.get_allocation()
        print('%-12s allocation=%dx%d' % (name, a.width, a.height))
    return 0


if __name__ == '__main__':
    sys.exit(main())
