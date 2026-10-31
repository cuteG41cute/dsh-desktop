#!/usr/bin/env python3
"""Render the manager window offscreen at a chosen size, with fixture data matching
design/index.html, so it can be diffed against the design reference.

  vm-gtk-shot.py OUTDIR [WxH] [combos] [pages]

  combos : comma list of theme:mode (default: every theme, day+night)
  pages  : comma list of dashboard,settings

No compositor involved: the window's child is moved into a Gtk.OffscreenWindow, so any
size works even though the VM screen is only 1280x720.
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
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk  # noqa: E402

from vm_fixture import DESIGN, FakeManager, inject_logs, pump  # noqa: E402


def setup(win, width, height):
    """把窗口内容搬进离屏窗口，返回 (offscreen, ManagerWindow)。"""
    child = win.get_child()
    win.remove(child)
    off = Gtk.OffscreenWindow()
    # 窗口背景（渐变 + 预渲染的 .scene 图）挂在 window.dsh-window 上；
    # 离屏窗口不加这个 class 就拍不到背景，夜间主题会变成半透明卡片浮在灰底上。
    off.get_style_context().add_class('dsh-window')
    off.set_default_size(width, height)
    off.set_size_request(width, height)
    off.add(child)
    off.show_all()
    off.resize(width, height)
    child.set_size_request(width, height)
    pump(200)
    off.resize(width, height)
    pump(600)
    return off


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gtk"
    size = sys.argv[2] if len(sys.argv) > 2 else "1392x852"
    width, height = (int(v) for v in size.lower().split("x"))
    combos = sys.argv[3] if len(sys.argv) > 3 else ""
    pages = (sys.argv[4] if len(sys.argv) > 4 else "dashboard,settings").split(",")
    os.makedirs(outdir, exist_ok=True)

    from dsh_manager import gui as g

    if not combos:
        combos = ",".join("%s:%s" % (t, m) for t in g.theme_index().get("order", [])
                          for m in ("day", "night"))

    win = g.ManagerWindow(manager=FakeManager())
    win.set_default_size(width, height)
    win.show_all()
    pump(700)
    win.selected = win.manager.instance_at(DESIGN["selected"])
    win.refresh()
    pump(500)
    inject_logs(win)
    pump(300)

    off = setup(win, width, height)
    print("offscreen alloc: %dx%d" % (off.get_allocated_width(), off.get_allocated_height()))

    wrote = 0
    for combo in [c for c in combos.split(",") if c.strip()]:
        theme, mode = combo.split(":") if ":" in combo else (combo, "day")
        ok = win.apply_theme(theme, mode, persist=False)
        pump(400)
        for page in pages:
            try:
                win._show_page(page.strip())
            except Exception as exc:
                print("page %s unsupported: %s" % (page, exc))
                continue
            pump(400)
            pb = off.get_pixbuf()
            if pb is None:
                print("FAIL: offscreen pixbuf is None")
                return 1
            path = os.path.join(outdir, "%s-%s-%s.png" % (theme, mode, page.strip()))
            pb.savev(path, "png", [], [])
            wrote += 1
            print("wrote %s %dx%d bytes=%d theme_ok=%s err=%s"
                  % (path, pb.get_width(), pb.get_height(), os.path.getsize(path),
                     ok, g.last_theme_error()))
    print("total %d images" % wrote)
    return 0


if __name__ == "__main__":
    sys.exit(main())
