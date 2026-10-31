#!/bin/bash
# 唤醒虚拟机的显示器（空闲后 Wayland 会 DPMS 关屏，portal 截图就变成纯黑），然后再截。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0

echo "== 解屏（KDE ScreenSaver + DPMS）=="
gdbus call --session --dest org.kde.screensaver --object-path /ScreenSaver \
  --method org.freedesktop.ScreenSaver.SetActive false 2>&1 | head -1
command -v xset >/dev/null && xset -dpms s off 2>/dev/null && echo "  xset -dpms ok"
if command -v xdotool >/dev/null; then
  xdotool mousemove 640 400 2>/dev/null && echo "  mousemove ok"
  xdotool key shift 2>/dev/null && echo "  key ok"
fi
sleep 2
echo "== 截图 =="
timeout 60 python3 /tmp/vm-shot.py /tmp/manager-awake.png 2>&1 | tail -2
ls -l /tmp/manager-awake.png 2>/dev/null
