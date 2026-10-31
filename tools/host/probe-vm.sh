#!/bin/bash
# Probe what a remote control channel can do on this VM session.
. /etc/os-release
echo "os=$PRETTY_NAME"
echo "user=$(id -un) uid=$(id -u)"
echo "== session procs"
pgrep -a kwin_wayland | head -3
pgrep -a plasmashell | head -2
echo "== tools"
for t in spectacle grim import ffmpeg gdbus dbus-send dbus-monitor python3 xdotool wmctrl scrot gnome-screenshot xwd gtk3-demo; do
  printf "%-18s %s\n" "$t" "$(command -v $t || echo MISSING)"
done
echo "== runtime dir"
ls "/run/user/$(id -u)" | head -20
echo "== sockets"
ls -l "/run/user/$(id -u)/wayland-"* "/run/user/$(id -u)/bus" 2>/dev/null
echo "== kwin env"
KPID=$(pgrep -x kwin_wayland | head -1)
echo "kwin pid=$KPID"
if [ -n "$KPID" ]; then
  tr '\0' '\n' < "/proc/$KPID/environ" 2>/dev/null | grep -E '^(XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DISPLAY|DBUS_SESSION_BUS_ADDRESS|XAUTHORITY|XDG_SESSION_TYPE|XDG_CURRENT_DESKTOP)='
fi
echo "== plasmashell env"
PPID2=$(pgrep -x plasmashell | head -1)
if [ -n "$PPID2" ]; then
  tr '\0' '\n' < "/proc/$PPID2/environ" 2>/dev/null | grep -E '^(XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DISPLAY|DBUS_SESSION_BUS_ADDRESS|XAUTHORITY)='
fi
echo "== display manager / seat"
loginctl list-sessions --no-legend 2>/dev/null | head -5
echo "== gpu"
ls /dev/dri 2>/dev/null
