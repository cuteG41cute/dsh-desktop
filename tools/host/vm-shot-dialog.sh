#!/bin/bash
# 打开插件对话框并截图（对话框由 vm-probe-dialog.py 自动弹出）。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
command -v kscreen-doctor >/dev/null && kscreen-doctor --dpms on >/dev/null 2>&1

pkill -f 'dsh_manager' 2>/dev/null
pkill -f '/usr/bin/dsh-manager' 2>/dev/null
sleep 1
LOG=/tmp/dialog-probe.log
: > "$LOG"
cd /home/twinblade/dsh-dev || exit 1
setsid nohup env PYTHONPATH=/home/twinblade/dsh-dev \
  python3 /tmp/vm-probe-dialog.py >> "$LOG" 2>&1 < /dev/null &
BGPID=$!
echo "probe pid=$BGPID"
sleep 8
echo "== log =="
cat "$LOG"
timeout 60 python3 /tmp/vm-shot.py /tmp/dialog.png 2>&1 | tail -1
ls -l /tmp/dialog.png 2>/dev/null
kill "$BGPID" 2>/dev/null
pkill -f 'vm-probe-dialog' 2>/dev/null
echo done
