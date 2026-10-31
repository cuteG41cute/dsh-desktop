#!/bin/bash
# Can GTK load SVG icons, and which fonts exist for CJK/Latin?
echo "== gdk-pixbuf loaders"
gdk-pixbuf-query-loaders 2>/dev/null | grep -iE '^\s*"' | grep -i svg || echo "  NO svg loader"
echo "== librsvg"
dpkg-query -W -f='${Version}\n' librsvg2-common 2>/dev/null || echo "  librsvg2-common missing"
echo "== latin sans candidates"
fc-list : family 2>/dev/null | tr ',' '\n' | grep -iE 'inter|noto sans$|dejavu sans|cantarell|liberation sans|ubuntu' | sort -u | head -12
echo "== CJK"
fc-list :lang=zh family 2>/dev/null | tr ',' '\n' | sort -u | head -8
echo "== what GTK uses now"
python3 - <<'PY'
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk
Gtk.init([])
settings = Gtk.Settings.get_default()
for k in ("gtk-font-name", "gtk-theme-name", "gtk-icon-theme-name"):
    print(" ", k, "=", settings.get_property(k) if settings else "?")
ls = Gtk.Label(label="x")
ctx = ls.get_style_context()
desc = ctx.get_property("font", Gtk.StateFlags.NORMAL) if False else None
print("  font-size-pt:", settings.get_property("gtk-xft-dpi"))
PY
