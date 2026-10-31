#!/usr/bin/env python3
"""Dump the GTK window's real geometry/typography as JSON, to compare with the
design spec produced by design-spec.mjs.

  vm-gtk-spec.py OUT.json [WxH] [theme] [mode] [page]

Walks the widget tree and records, for widgets carrying a design-ish style class,
their allocation in window coordinates plus the resolved font size/weight.
"""
import json
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

WANT = {
    "shell", "sidebar", "brand", "brand-mark", "side-section-title", "instance-list",
    "instance-item", "instance-avatar", "new-instance", "sidebar-bottom", "side-caption",
    "side-link", "runtime", "runtime-icon", "main-panel", "topbar", "breadcrumb",
    "top-actions", "theme-trigger", "mode-toggle", "content", "page-heading", "eyebrow",
    "title-line", "status-badge", "heading-actions", "btn", "btn-primary", "btn-secondary",
    "overview-grid", "card", "instance-card", "control-card", "card-label", "subtle-tag",
    "large-avatar", "meta-main", "version-pills", "metric-row", "quick-section",
    "section-heading", "quick-grid", "quick-action", "quick-icon", "log-card",
    "log-header", "log-line", "log-title", "page-footer", "instance-name", "instance-sub",
    "settings-layout", "settings-card", "instance-copy",
    "page-title", "page-desc", "section-title", "section-sub", "quick-title", "quick-sub",
    "metric-label", "metric-value", "log-time", "log-level", "control-title", "control-sub",
    "brand-title", "brand-sub", "log-empty", "top-divider", "mode-toggle", "theme-trigger",
}


def walk(widget, out, root, depth=0):
    try:
        classes = widget.get_style_context().list_classes() or []
    except Exception:
        classes = []
    keep = [c for c in classes if c in WANT]
    if keep and widget.get_visible():
        try:
            res = widget.translate_coordinates(root, 0, 0)
            if len(res) == 3:
                _ok, x, y = res
            else:
                x, y = res
        except Exception:
            x = y = None
        alloc = widget.get_allocation()
        rec = {
            "name": widget.get_name(),
            "classes": keep,
            "x": round(x, 2) if x is not None else None,
            "y": round(y, 2) if y is not None else None,
            "w": alloc.width,
            "h": alloc.height,
            "depth": depth,
        }
        try:
            # style_context.get_property('font') 在 GTK3 里经常取不到，
            # 改用 Pango 上下文：字号单位是 1/PANGO_SCALE pt，换算成 px 才能和设计稿比。
            ctx = widget.create_pango_context()
            desc = ctx.get_font_description()
            pt = desc.get_size() / 1024.0
            rec["font_px"] = round(pt * 96.0 / 72.0, 2)
            rec["weight"] = int(desc.get_weight() or 0)
            rec["family"] = desc.get_family() or ""
        except Exception:
            pass
        if isinstance(widget, Gtk.Label):
            text = widget.get_text() or ""
            if text:
                rec["text"] = text[:60]
        out.append(rec)
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            walk(child, out, root, depth + 1)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gtk-spec.json"
    width, height = (int(v) for v in (sys.argv[2] if len(sys.argv) > 2 else "1392x852").split("x"))
    theme = sys.argv[3] if len(sys.argv) > 3 else "frost"
    mode = sys.argv[4] if len(sys.argv) > 4 else "day"
    page = sys.argv[5] if len(sys.argv) > 5 else "dashboard"

    from dsh_manager import gui as g

    win = g.ManagerWindow(manager=FakeManager())
    win.set_default_size(width, height)
    win.show_all()
    pump(600)
    win.selected = win.manager.instance_at(DESIGN["selected"])
    win.refresh()
    pump(400)
    win.apply_theme(theme, mode, persist=False)
    pump(300)
    win._show_page(page)
    pump(400)
    inject_logs(win)
    pump(300)

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

    recs = []
    walk(off, recs, off)
    data = {
        "size": [off.get_allocated_width(), off.get_allocated_height()],
        "theme": theme, "mode": mode, "page": page,
        "gtk_version": "%d.%d.%d" % (Gtk.get_major_version(), Gtk.get_minor_version(),
                                     Gtk.get_micro_version()),
        "widgets": recs,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print("wrote %s: %d widgets" % (out_path, len(recs)))
    seen = set()
    for rec in recs:
        key = rec["classes"][0]
        if key in seen:
            continue
        seen.add(key)
        print("  %-26s %-18s x=%-7s y=%-7s %sx%s font_px=%s"
              % (rec["name"][:26], key, rec["x"], rec["y"], rec["w"], rec["h"],
                 rec.get("font_px")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
