#!/bin/bash
# 用暗色主题打开插件对话框并截图，验证"子窗口随主题变化"。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
export DSH_PROBE_THEME=sea
export DSH_PROBE_MODE=night
command -v kscreen-doctor >/dev/null && kscreen-doctor --dpms on >/dev/null 2>&1

pkill -f 'dsh_manager' 2>/dev/null
pkill -f '/usr/bin/dsh-manager' 2>/dev/null
sleep 1
LOG=/tmp/dialog-night.log
: > "$LOG"
cd /home/twinblade/dsh-dev || exit 1
setsid nohup env PYTHONPATH=/home/twinblade/dsh-dev DSH_PROBE_THEME=sea DSH_PROBE_MODE=night \
  python3 /tmp/vm-probe-dialog.py >> "$LOG" 2>&1 < /dev/null &
BGPID=$!
sleep 8
cat "$LOG"
timeout 60 python3 /tmp/vm-shot.py /tmp/dialog-night.png 2>&1 | tail -1
kill "$BGPID" 2>/dev/null
pkill -f 'vm-probe-dialog' 2>/dev/null
echo done
