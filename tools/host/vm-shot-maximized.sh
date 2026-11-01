#!/bin/bash
# 起来一个最大化的窗口（后台），等它稳住后截图，然后收掉。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
command -v kscreen-doctor >/dev/null && kscreen-doctor --dpms on >/dev/null 2>&1

pkill -f 'dsh_manager' 2>/dev/null
pkill -f '/usr/bin/dsh-manager' 2>/dev/null
sleep 1

LOG=/tmp/max-probe.log
: > "$LOG"
cd /home/twinblade/dsh-dev || exit 1
setsid nohup env PYTHONPATH=/home/twinblade/dsh-dev \
  python3 /tmp/vm-probe-maximize.py >> "$LOG" 2>&1 < /dev/null &
BGPID=$!
echo "probe pid=$BGPID"
sleep 8
echo "== 探测日志 =="
cat "$LOG"
echo "== 截图 =="
timeout 60 python3 /tmp/vm-shot.py /tmp/maximized.png 2>&1 | tail -2
ls -l /tmp/maximized.png 2>/dev/null
kill "$BGPID" 2>/dev/null
pkill -f 'vm-probe-maximize' 2>/dev/null
echo done
