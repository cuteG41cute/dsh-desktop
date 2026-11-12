#!/bin/bash
# Drag test with sudo'd ydotool (socket is root-only).
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

yd() { sudo -n env YDOTOOL_SOCKET=/tmp/.ydotool_socket ydotool "$@"; }

shot() {
  local name=$1
  rm -f /home/twinblade/图片/Screenshot.png
  gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
    --method org.freedesktop.portal.Screenshot.Screenshot "" "{}" >/dev/null 2>&1
  for i in $(seq 1 10); do
    sleep 1
    if [ -f /home/twinblade/图片/Screenshot.png ]; then
      cp /home/twinblade/图片/Screenshot.png "/home/twinblade/图片/$name"
      rm -f /home/twinblade/图片/Screenshot.png
      echo "shot $name ok"
      return 0
    fi
  done
  echo "shot $name FAILED"
}

echo "=== 取窗口位置（用 gdbus? 不行：直接看截图）==="
shot drag-before.png

echo "=== 模拟：标题栏按下 + 拖动 ==="
yd mousemove --absolute -x 700 -y 120 || true
sleep 0.4
yd click 0x40 || echo "down failed"
sleep 0.3
for x in 730 770 810 850; do yd mousemove --absolute -x $x -y 180 || true; sleep 0.15; done
yd click 0x80 || echo "up failed"
sleep 0.8

shot drag-after.png
ls -l /home/twinblade/图片/drag-before.png /home/twinblade/图片/drag-after.png 2>/dev/null
