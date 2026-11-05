#!/bin/bash
# Open the plugin dialog using the INSTALLED package (/usr/lib/dsh-manager) and screenshot it.
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
export XAUTHORITY=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
export LIBGL_ALWAYS_SOFTWARE=1
export PYTHONPATH=/usr/lib/dsh-manager

cat > /tmp/installed-drive.py <<'PY'
# -*- coding: utf-8 -*-
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from dsh_manager import gui
from dsh_manager.core import Manager, MANAGER_VERSION

def pump(s):
    end = time.time() + s
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.05)

print('installed version:', MANAGER_VERSION)
win = gui.ManagerWindow(Manager())
win.show_all()
pump(2.0)
rows = list(win.instance_list.get_children())
if rows:
    win.instance_list.select_row(rows[0])
    pump(0.8)
win.on_plugins()
pump(3.0)
for d in Gtk.Window.list_toplevels():
    if isinstance(d, Gtk.Window) and d.get_visible():
        print('win %r modal=%s' % (d.get_title(), d.get_modal()))
for _ in range(40):
    pump(0.5)
PY

cd /usr/lib/dsh-manager || exit 1
setsid nohup python3 /tmp/installed-drive.py > /tmp/align/installed.log 2>&1 < /dev/null &
sleep 10
cat /tmp/align/installed.log
python3 /tmp/vm-shot.py /tmp/align/installed-plugin.png portal 2>&1 | tail -2
pkill -f installed-drive.py 2>/dev/null
