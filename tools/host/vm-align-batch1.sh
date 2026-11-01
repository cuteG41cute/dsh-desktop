#!/bin/bash
# Batch-1 verification for the Linux manager: frameless + modeless dialogs.
# Unpacks the freshly uploaded source, opens the manager, opens the plugin dialog,
# prints the dialog flags and renders both windows to PNG.
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
export XAUTHORITY=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
export LIBGL_ALWAYS_SOFTWARE=1
export PYTHONPATH="$HOME/dsh-dev"

cd "$HOME" || exit 1
rm -rf "$HOME/dsh-dev"
mkdir -p "$HOME/dsh-dev"
tar -xzf /tmp/manager-dev.tgz -C "$HOME/dsh-dev" || { echo "unpack failed"; exit 1; }
echo "== source unpacked: $(ls "$HOME/dsh-dev/dsh_manager" | tr '\n' ' ')"

mkdir -p /tmp/align
cat > /tmp/align-drive.py <<'PY'
# -*- coding: utf-8 -*-
import os, sys, time
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from dsh_manager import gui
from dsh_manager.core import Manager

def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.05)

win = gui.ManagerWindow(Manager())
win.show_all()
pump(2.0)

# 选中第一个实例，再打开插件对话框
rows = []
for r in win.instance_list.get_children():
    rows.append(r)
print('rows=%d' % len(rows))
if rows:
    win.instance_list.select_row(rows[0])
    pump(1.0)

try:
    win.on_plugins()
except Exception as exc:
    print('on_plugins raised: %r' % (exc,))
pump(2.5)

tops = [w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.Window)]
dialogs = [w for w in tops if w is not win and w.get_visible()]
print('top-level windows: %d, visible dialogs: %d' % (len(tops), len(dialogs)))
for d in dialogs:
    alloc = d.get_allocation()
    print('  dialog title=%r modal=%s decorated=%s size=%dx%d' % (
        d.get_title(), d.get_modal(), d.get_decorated(), alloc.width, alloc.height))

def shot(w, path):
    try:
        gdkwin = w.get_window()
        if gdkwin is None:
            print('no gdk window for %s' % path)
            return
        ww, wh = gdkwin.get_width(), gdkwin.get_height()
        pb = Gdk.pixbuf_get_from_window(gdkwin, 0, 0, ww, wh)
        if pb is None:
            print('pixbuf None for %s' % path)
            return
        pb.savev(path, 'png', [], [])
        print('saved %s (%dx%d)' % (path, ww, wh))
    except Exception as exc:
        print('shot failed %s: %r' % (path, exc))

pump(0.5)
shot(win, '/tmp/align/manager.png')
for i, d in enumerate(dialogs):
    shot(d, '/tmp/align/dialog%d.png' % i)

# 关键验证：非模态 = 管理器窗口仍然可交互（GTK 的 modal 会让父窗口 insensitive）
print('manager sensitive=%s' % win.get_sensitive())
pump(0.3)
Gtk.main_quit()
PY

cd "$HOME/dsh-dev" && python3 /tmp/align-drive.py 2>&1 | tail -30
echo "== shots"
ls -la /tmp/align/ 2>/dev/null
