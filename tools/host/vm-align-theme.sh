#!/bin/bash
# Batch-4 verification: manager day/night must reach the DSH page (prefers-color-scheme).
# 1) the manager really exports DSH_DESKTOP_MODE
# 2) the window process turns that into a dark/light GTK preference and the page follows
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

echo "== 1) manager exports DSH_DESKTOP_MODE"
cat > /tmp/align-theme-driver.py <<'PY'
# -*- coding: utf-8 -*-
import os, time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from dsh_manager import gui
from dsh_manager.core import Manager

def pump(s):
    end = time.time() + s
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.05)

win = gui.ManagerWindow(Manager())
win.show_all()
pump(1.5)
win.apply_theme('frost', 'night', persist=False)
pump(0.5)
print('after night -> DSH_DESKTOP_MODE=%r' % os.environ.get('DSH_DESKTOP_MODE'))
win.apply_theme('frost', 'day', persist=False)
pump(0.5)
print('after day   -> DSH_DESKTOP_MODE=%r' % os.environ.get('DSH_DESKTOP_MODE'))
PY
cd "$HOME/dsh-dev" && python3 /tmp/align-theme-driver.py 2>&1 | grep -E "DSH_DESKTOP_MODE|Traceback" | head -5

echo "== 2) window process follows it (mean brightness of the page)"
SHARE="$HOME/.local/opt/deepseek-harness-2/share"
cp -f /tmp/dsh-desktop.py "$SHARE/dsh-desktop.py" 2>/dev/null || true

shoot() {  # $1 = day|night, $2 = output png
  DSH_DESKTOP_MODE="$1" setsid nohup python3 "$SHARE/dsh-desktop.py" \
      "http://127.0.0.1:3081" > "/tmp/align/win-$1.log" 2>&1 < /dev/null &
  W=$!
  sleep 16
  python3 /tmp/vm-shot.py "$2" portal >/dev/null 2>&1
  kill $W 2>/dev/null
  pkill -f "dsh-desktop.py http://127.0.0.1:3081" 2>/dev/null
  sleep 1
  grep -E "跟随管理器主题" "/tmp/align/win-$1.log" | head -2
}

shoot night /tmp/align/night.png
shoot day /tmp/align/day.png

python3 - <<'PY'
from PIL import Image
for name in ('night', 'day'):
    try:
        im = Image.open('/tmp/align/%s.png' % name).convert('L')
        w, h = im.size
        box = im.crop((int(w * 0.25), int(h * 0.2), int(w * 0.45), int(h * 0.5)))
        px = list(box.getdata())
        print('%-5s mean brightness = %.1f' % (name, sum(px) / len(px)))
    except Exception as exc:
        print('%s: %r' % (name, exc))
PY
