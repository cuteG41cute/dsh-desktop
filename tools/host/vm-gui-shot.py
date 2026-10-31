#!/usr/bin/env python3
"""Render the real manager GUI offscreen on the VM and write PNGs.

No compositor involved: the window is built for real (theme CSS, widgets, live
data), pumped through GLib, then drawn into a cairo surface with GTK's own
renderer. That makes the output deterministic and independent of window stacking,
so it is usable for pixel comparison against design/references/.

  vm-gui-shot.py OUTDIR [pages] [combos]

  pages  : comma list, default "dashboard,settings"
  combos : comma list of theme:mode, default = every theme index entry

Example:
  vm-gui-shot.py /tmp/gui dashboard,files frost:day,frost:night
"""
import os
import sys
import time
import traceback

RUNTIME = "/run/user/%d" % os.getuid()
os.environ.setdefault("XDG_RUNTIME_DIR", RUNTIME)
os.environ.setdefault("DISPLAY", ":1")
os.environ.setdefault("GDK_BACKEND", "x11")
os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=%s/bus" % RUNTIME)
for entry in os.listdir(RUNTIME):
    if entry.startswith("xauth_"):
        os.environ.setdefault("XAUTHORITY", os.path.join(RUNTIME, entry))

sys.path.insert(0, os.path.expanduser("~/dsh-dev"))

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

HAVE_FOREIGN_CAIRO = True
try:
    gi.require_foreign("cairo")
except Exception:
    HAVE_FOREIGN_CAIRO = False


def pump(ms=300):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.005)


def render(win, path, width=None, height=None):
    """Capture the app's own window. X11 backend: XGetImage on our own XID."""
    w = width or win.get_allocated_width()
    h = height or win.get_allocated_height()
    gw = win.get_window()
    if gw is not None:
        try:
            pb = Gdk.pixbuf_get_from_window(gw, 0, 0, w, h)
            if pb is not None:
                pb.savev(path, "png", [], [])
                return path
        except Exception as exc:
            print("pixbuf capture failed: %s" % exc)
    if not HAVE_FOREIGN_CAIRO:
        raise RuntimeError("no capture path: pixbuf failed and python3-gi-cairo missing")
    import cairo
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    ctx = win.get_style_context()
    try:
        Gtk.render_background(ctx, cr, 0, 0, w, h)
    except Exception:
        pass
    win.draw(cr)
    surf.write_to_png(path)
    return path


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gui"
    pages = (sys.argv[2] if len(sys.argv) > 2 else "dashboard,settings").split(",")
    combos = sys.argv[3] if len(sys.argv) > 3 else ""

    os.makedirs(outdir, exist_ok=True)

    from dsh_manager import gui as g

    print("theme_index:", g.theme_index().get("order"))
    if not combos:
        combos = ",".join("%s:%s" % (t, m) for t in g.theme_index().get("order", [])
                          for m in ("day", "night"))

    win = g.ManagerWindow()
    win.set_default_size(1280, 760)
    win.show_all()
    pump(700)

    results = []
    pages_real = {"dashboard": "dashboard", "settings": "settings", "instances": "instances",
                  "about": "about", "help": "help", "files": "files"}
    nav = getattr(win, "nav_items", {})
    if nav:
        print("nav items:", list(nav.keys()))

    for combo in [c for c in combos.split(",") if c.strip()]:
        theme, mode = combo.split(":") if ":" in combo else (combo, "day")
        ok = win.apply_theme(theme, mode, persist=False)
        pump(450)
        for page in pages:
            name = pages_real.get(page.strip(), page.strip())
            try:
                win._show_page(name)
            except Exception as exc:
                print("page %s unsupported: %s" % (name, exc))
                continue
            pump(400)
            path = os.path.join(outdir, "%s-%s-%s.png" % (theme.strip(), mode, name))
            render(win, path)
            results.append((path, ok, g.last_theme_error()))
            print("wrote %s (%d bytes, theme_ok=%s, err=%s)"
                  % (path, os.path.getsize(path), ok, g.last_theme_error()))

    win.destroy()
    pump(100)
    print("total %d images" % len(results))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
