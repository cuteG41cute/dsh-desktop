#!/bin/bash
# Clean up: stop the dev copy I launched, keep the installed 1.3.3 GUI, report state.
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade

echo "== kill dev instance (source-run from ~/dsh-dev only)"
pkill -f 'from dsh_manager.cli import main' 2>/dev/null && echo "  dev instance stopped" || echo "  no dev instance"
sleep 1
echo "== survivors"
ps -eo pid,cmd | grep -E 'dsh-manager|dsh_manager' | grep -v grep || echo "  none"
echo "== installed GUI log tail"
tail -5 /tmp/dsh-manager-gui-wayland.log 2>/dev/null || echo "  (no log)"
echo "== share contents"
ls -l "$HOME/share"
