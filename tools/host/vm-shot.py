#!/usr/bin/env python3
"""Take a screenshot of the live KDE/Wayland session from a plain SSH shell.

Order of preference: xdg-desktop-portal Screenshot (writes a PNG) -> KWin
ScreenShot2 (raw pixels) -> xwd over Xwayland.

  shot.py OUT.png                 # full screen, auto
  shot.py OUT.png portal          # force one backend
  shot.py OUT.png kwin
  shot.py OUT.png xwd
  shot.py OUT.png area:0,0,1280,720
"""
import os
import shutil
import sys
import tempfile
import time
import urllib.parse

from gi.repository import Gio, GLib

RUNTIME = "/run/user/%d" % os.getuid()


def setup_env():
    os.environ.setdefault("XDG_RUNTIME_DIR", RUNTIME)
    os.environ.setdefault("DISPLAY", ":1")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    os.environ.setdefault("GDK_BACKEND", "wayland")
    wl = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
    if os.path.exists(os.path.join(RUNTIME, wl + ".lock")):
        for entry in os.listdir(RUNTIME):
            if entry.startswith("xauth_"):
                os.environ.setdefault("XAUTHORITY", os.path.join(RUNTIME, entry))


def session_bus():
    setup_env()
    addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS") or "unix:path=%s/bus" % RUNTIME
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = addr
    flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
    return Gio.DBusConnection.new_for_address_sync(addr, flags, None, None)


def portal_screenshot(bus, out, interactive=False):
    token = "dshshot%d" % os.getpid()
    sender = bus.get_unique_name().lstrip(":").replace(".", "_")
    predicted = "/org/freedesktop/portal/desktop/request/%s/%s" % (sender, token)
    box = {}
    loop = GLib.MainLoop()

    def on_response(conn, sender_name, path, iface, signal, params):
        if path != predicted:
            return
        code, results = params.unpack()
        box["code"] = code
        box["uri"] = results.get("uri")
        loop.quit()

    sub = bus.signal_subscribe(
        "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request",
        "Response", predicted, None, Gio.DBusSignalFlags.NONE, on_response)

    def on_timeout():
        box["timeout"] = True
        loop.quit()
        return False

    timer = GLib.timeout_add_seconds(45, on_timeout)
    options = {
        "handle_token": GLib.Variant("s", token),
        "interactive": GLib.Variant("b", interactive),
        "modal": GLib.Variant("b", False),
    }
    try:
        (path,) = bus.call_sync(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot", "Screenshot",
            GLib.Variant("(sa{sv})", ("", options)), None,
            Gio.DBusCallFlags.NONE, 30000, None).unpack()
    except Exception as exc:
        bus.signal_unsubscribe(sub)
        GLib.source_remove(timer)
        raise RuntimeError("portal call failed: %s" % exc)

    if path != predicted:
        # portal chose another object path: re-subscribe before it fires
        bus.signal_unsubscribe(sub)
        sub = bus.signal_subscribe(
            "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request",
            "Response", path, None, Gio.DBusSignalFlags.NONE, on_response)

    loop.run()
    bus.signal_unsubscribe(sub)
    try:
        GLib.source_remove(timer)
    except Exception:
        pass

    if box.get("timeout"):
        raise RuntimeError("portal response timed out (user dialog pending?)")
    if box.get("code") != 0:
        raise RuntimeError("portal returned code %s" % box.get("code"))
    uri = box.get("uri")
    if not uri:
        raise RuntimeError("portal returned no uri")
    src = urllib.parse.unquote(uri.replace("file://", "", 1))
    shutil.copyfile(src, out)
    os.unlink(src)
    return out


def kwin_capture(bus, out, area=None):
    """KWin ScreenShot2 writes raw ARGB32 pixels into an fd we supply."""
    from PIL import Image

    tmp = tempfile.NamedTemporaryFile(prefix="dsnshot", suffix=".raw", dir="/tmp", delete=False)
    tmp.close()
    fobj = open(tmp.name, "r+b")
    fds = Gio.UnixFDList.new()
    fds.append(fobj.fileno())
    options = {"include-cursor": GLib.Variant("b", False), "native-resolution": GLib.Variant("b", True)}
    try:
        if area:
            x, y, w, h = area
            args = GLib.Variant("(iiiia{sv}h)", (x, y, w, h, options, 0))
            method = "CaptureArea"
        else:
            args = GLib.Variant("(a{sv}h)", (options, 0))
            method = "CaptureActiveScreen"
        ret = bus.call_with_unix_fd_list_sync(
            "org.kde.KWin", "/org/kde/KWin/ScreenShot2", "org.kde.KWin.ScreenShot2",
            method, args, GLib.VariantType.new("(a{sv})"),
            Gio.DBusCallFlags.NONE, 30000, fds, None)
    finally:
        fobj.close()
    reply, _out_fds = ret
    results = reply.unpack()[0]
    wd = int(results["width"])
    ht = int(results["height"])
    stride = int(results["stride"])
    with open(tmp.name, "rb") as fh:
        data = fh.read()
    os.unlink(tmp.name)
    if len(data) < stride * ht:
        raise RuntimeError("short pixel buffer: %d < %d" % (len(data), stride * ht))
    img = Image.frombuffer("RGBA", (wd, ht), data, "raw", "BGRA", stride, 1)
    img.convert("RGB").save(out)
    return out


def xwd_capture(out, display=":1"):
    """Fallback: root window of Xwayland (only X11 windows show up)."""
    from PIL import Image

    tmp = tempfile.NamedTemporaryFile(prefix="dshxwd", suffix=".xwd", dir="/tmp", delete=False)
    tmp.close()
    rc = os.system("xwd -root -silent -display %s -out %s" % (display, tmp.name))
    if rc != 0:
        raise RuntimeError("xwd failed rc=%d" % rc)
    with open(tmp.name, "rb") as fh:
        head = fh.read(100)
        hsize = int.from_bytes(head[0:4], "big")
        fh.seek(0)
        raw = fh.read()
    os.unlink(tmp.name)
    # xwd v7 header fields
    import struct
    hdr = struct.unpack(">25I", raw[:hsize])
    width, height = hdr[4], hdr[5]
    pixmap_format, bits_per_pixel = hdr[7], hdr[11]
    bytes_per_line = hdr[12]
    pix = raw[hsize:]
    if bits_per_pixel != 32:
        raise RuntimeError("xwd bits_per_pixel=%d unsupported" % bits_per_pixel)
    img = Image.frombuffer("RGBA", (width, height), pix, "raw", "BGRA", bytes_per_line, 1)
    img.convert("RGB").save(out)
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out = os.path.abspath(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else "auto"
    area = None
    if mode.startswith("area:"):
        area = list(map(int, mode[5:].split(",")))
        mode = "kwin"
    order = [mode] if mode != "auto" else ["portal", "kwin", "xwd"]
    errors = []
    for backend in order:
        try:
            if backend == "portal":
                portal_screenshot(session_bus(), out)
            elif backend == "kwin":
                kwin_capture(session_bus(), out, area)
            elif backend == "xwd":
                xwd_capture(out)
            else:
                raise RuntimeError("unknown mode %s" % backend)
            size = os.path.getsize(out)
            print("ok %s backend=%s bytes=%d" % (out, backend, size))
            return 0
        except Exception as exc:
            errors.append("%s: %s" % (backend, exc))
    print("all backends failed:\n  " + "\n  ".join(errors))
    return 1


if __name__ == "__main__":
    sys.exit(main())
