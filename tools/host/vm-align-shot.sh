#!/bin/bash
# Batch-1 verification (screen capture version): show manager + plugin dialog,
# then take a real portal screenshot of the desktop.
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
export XAUTHORITY=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
export LIBGL_ALWAYS_SOFTWARE=1
export PYTHONPATH="$HOME/dsh-dev"

rm -rf "$HOME/dsh-dev"; mkdir -p "$HOME/dsh-dev"
tar -xzf /tmp/manager-dev.tgz -C "$HOME/dsh-dev" || { echo "unpack failed"; exit 1; }
mkdir -p /tmp/align

cat > /tmp/align-drive.py <<'PY'
# -*- coding: utf-8 -*-
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

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
rows = list(win.instance_list.get_children())
print('rows=%d' % len(rows))
if rows:
    win.instance_list.select_row(rows[0])
    pump(1.0)
try:
    win.on_plugins()
except Exception as exc:
    print('on_plugins raised: %r' % (exc,))
pump(3.0)
for d in Gtk.Window.list_toplevels():
    if isinstance(d, Gtk.Window) and d.get_visible():
        print('win title=%r modal=%s decorated=%s' % (
            d.get_title(), d.get_modal(), d.get_decorated()))
print('manager sensitive=%s' % win.get_sensitive())
print('READY-FOR-SHOT')
import sys
sys.stdout.flush()
# 保持窗口可见，等外部截图
for _ in range(60):
    pump(0.5)
PY

cd "$HOME/dsh-dev" || exit 1
setsid nohup python3 /tmp/align-drive.py > /tmp/align/drive.log 2>&1 < /dev/null &
DRIVE=$!
sleep 9
echo "== driver log"
cat /tmp/align/drive.log
echo "== portal shot"
python3 /tmp/vm-shot.py /tmp/align/screen.png portal 2>&1 | tail -5
kill $DRIVE 2>/dev/null
pkill -f align-drive.py 2>/dev/null
sleep 0.5
ls -la /tmp/align/
