#!/bin/bash
# Verify window drag + edge resize with simulated input (ydotool) and screenshots.
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export YDOTOOL_SOCKET=/run/user/1000/.ydotool_socket

echo "=== 启动 ydotoold ==="
pkill -f ydotoold 2>/dev/null || true
sudo -n bash -c 'YDOTOOL_SOCKET=/run/user/1000/.ydotool_socket setsid ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 2
ls -l /run/user/1000/.ydotool_socket 2>/dev/null || echo '(no socket)'
tail -3 /tmp/ydotoold.log 2>/dev/null || true

shot() {
  rm -f "/home/twinblade/图片/$1"
  gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
    --method org.freedesktop.portal.Screenshot.Screenshot "" "{}" >/dev/null 2>&1
  for i in $(seq 1 10); do
    sleep 1
    [ -f /home/twinblade/图片/Screenshot.png ] && { mv /home/twinblade/图片/Screenshot.png "/home/twinblade/图片/$1"; return 0; }
  done
  echo "(shot $1 failed)"
}

echo "=== 拖拽前 ==="
shot before.png

echo "=== 在标题栏按下并拖动 ==="
ydotool mousemove --absolute -x 700 -y 120 2>&1 || ydotool mousemove 700 120 2>&1
sleep 0.5
# ydotool click 0xC0 = 左键按下，0xC1? 用 click 的 down/up 语法
ydotool click --down 1 2>/dev/null || ydotool click 0x40
sleep 0.3
for x in 740 780 820; do ydotool mousemove --absolute -x $x -y 190 2>/dev/null || ydotool mousemove $x 190; sleep 0.2; done
ydotool click --up 1 2>/dev/null || ydotool click 0x80
sleep 0.5

echo "=== 拖拽后 ==="
shot after.png
ls -l /home/twinblade/图片/before.png /home/twinblade/图片/after.png 2>/dev/null
