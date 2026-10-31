#!/bin/bash
# Run the *dev copy* of the manager on the VM (no root, no /usr writes) and screenshot it.
# Expects /tmp/manager-dev.tgz already uploaded (contains dsh_manager/).
#
#   vm-run-dev-manager.sh [out.png] [extra-python-args...]
set -u
OUT="${1:-/tmp/dev-manager.png}"
shift || true

export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
[ -n "${XA:-}" ] && export XAUTHORITY="$XA"
export HOME=/home/twinblade
export GDK_BACKEND=wayland
export LIBGL_ALWAYS_SOFTWARE=1

DEV="$HOME/dsh-dev"
echo "== unpack dev tree to $DEV"
rm -rf "$DEV"
mkdir -p "$DEV"
tar xzf /tmp/manager-dev.tgz -C "$DEV" || { echo "unpack failed"; exit 1; }
echo "version: $(grep -m1 -r 'MANAGER_VERSION' "$DEV/dsh_manager/__init__.py" 2>/dev/null)"
du -sh "$DEV/dsh_manager"

pkill -f 'dsh_manager' 2>/dev/null
pkill -f '/usr/bin/dsh-manager' 2>/dev/null
sleep 1

LOG=/tmp/dsh-dev-manager.log
: > "$LOG"
cd "$DEV" || exit 1
setsid nohup env PYTHONPATH="$DEV" python3 -c 'import sys; sys.argv=["dsh-manager"]; from dsh_manager.cli import main; sys.exit(main())' >> "$LOG" 2>&1 < /dev/null &
PID=$!
echo "launched dev pid=$PID"
for i in $(seq 1 10); do
  sleep 1
  kill -0 "$PID" 2>/dev/null || { echo "exited after ${i}s"; break; }
done
ps -o pid,etime,cmd -p "$PID" 2>/dev/null || echo "not running"
echo "== log"
tail -20 "$LOG"
echo "== screenshot"
timeout 60 python3 /tmp/vm-shot.py "$OUT" 2>&1 | tail -3
ls -l "$OUT" 2>/dev/null
