#!/bin/bash
# Upload-and-run helper for the two files: fix focus via KWin script, then screenshot.
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0

echo "== run kwin script"
bash /tmp/vm-kwin-script.sh /tmp/kwin-fix-focus.js
sleep 2
echo "== screenshot"
timeout 60 python3 /tmp/vm-shot.py /tmp/manager-clean.png 2>&1 | tail -3
ls -l /tmp/manager-clean.png 2>/dev/null
