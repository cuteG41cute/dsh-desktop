#!/bin/bash
# Batch-3 verification: instance row text (版本 · 端口 · PID) + the desktop window really
# opens the instance port directly (no mobile bridge).
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

cat > /tmp/align-drive3.py <<'PY'
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
for r in rows:
    inst = getattr(r, 'inst', None)
    sub = getattr(r, 'sub', None)
    print('  name=%-28r sub=%r' % (
        inst.label if inst else None, sub.get_text() if sub is not None else None))

if rows:
    win.instance_list.select_row(rows[0])
    pump(1.0)
    print('opening window for %r ...' % rows[0].inst.label)
    try:
        win.on_open()
    except Exception as exc:
        print('on_open raised: %r' % (exc,))
    pump(14.0)
    print('done-wait')
PY

cd "$HOME/dsh-dev" || exit 1
python3 /tmp/align-drive3.py 2>&1 | tail -20
echo "== desktop window process cmdline (should be http://127.0.0.1:<port>, no 8099)"
ps -eo pid,cmd | grep -E "dsh-desktop" | grep -v grep | head -6
echo "== portal shot"
python3 /tmp/vm-shot.py /tmp/align/batch3.png portal 2>&1 | tail -3
