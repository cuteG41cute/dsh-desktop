#!/bin/bash
# Why did the KWin script do nothing, and is there a DebugConsole object to close?
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"

echo "== kwin dbus objects"
gdbus introspect --session --dest org.kde.KWin --object-path / --recurse 2>&1 | grep -E '^node |interface ' | head -40

echo "== journal tail (kwin / scripting errors)"
journalctl --user -n 200 --no-pager 2>/dev/null | grep -iE 'kwin|script' | tail -20
