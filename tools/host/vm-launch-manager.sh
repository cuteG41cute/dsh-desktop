#!/bin/bash
# Launch the installed dsh-manager GUI inside the live KDE session, wait, screenshot.
#   vm-launch-manager.sh [wayland|x11] [out.png] [wait-seconds]
set -u
MODE="${1:-wayland}"
OUT="${2:-/tmp/manager.png}"
WAIT="${3:-9}"

export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
[ -n "${XA:-}" ] && export XAUTHORITY="$XA"
export HOME=/home/twinblade

# 虚拟机的屏幕空闲后会被 DPMS 关掉，这时 portal/kwin 截图全是纯黑（实测整幅 mean=0）。
# 每次启动/截图前先强制点亮。
command -v kscreen-doctor >/dev/null && kscreen-doctor --dpms on >/dev/null 2>&1

case "$MODE" in
  x11) export GDK_BACKEND=x11 ;;
  *)   export GDK_BACKEND=wayland ;;
esac
export LIBGL_ALWAYS_SOFTWARE=1

pkill -f '/usr/bin/dsh-manager' 2>/dev/null
sleep 1
LOG=/tmp/dsh-manager-gui-$MODE.log
: > "$LOG"
setsid nohup /usr/bin/dsh-manager >> "$LOG" 2>&1 < /dev/null &
LPID=$!
echo "launched pid=$LPID mode=$MODE log=$LOG"
for i in $(seq 1 "$WAIT"); do
  sleep 1
  if ! kill -0 "$LPID" 2>/dev/null; then
    echo "process exited after ${i}s"
    break
  fi
done
echo "== ps"
ps -o pid,etime,cmd -p "$LPID" 2>/dev/null || echo "not running"
echo "== window list"
if [ -f /tmp/vm-kwin-script.sh ] && [ -f /tmp/kwin-fix-focus.js ]; then
  bash /tmp/vm-kwin-script.sh /tmp/kwin-fix-focus.js
  sleep 2
fi
echo "== log"
tail -25 "$LOG"
echo "== screenshot"
timeout 60 python3 /tmp/vm-shot.py "$OUT" 2>&1 | tail -3
ls -l "$OUT" 2>/dev/null
