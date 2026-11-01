#!/bin/bash
# 1) 当前桌面窗口的实时日志；2) 激活窗口是否在被反复切换（切焦点会让所有菜单关掉）。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade

echo '== 桌面窗口实时日志（/tmp/dsh-desktop-live.log 尾部 30 行）'
tail -30 /tmp/dsh-desktop-live.log 2>/dev/null || echo '  （没有这个文件）'

echo
echo '== 激活窗口采样（每 0.4 秒一次，看是否在切换）'
for i in $(seq 1 12); do
  w=$(qdbus org.kde.KWin /KWin activeWindow 2>/dev/null | head -1)
  a=$(qdbus org.kde.KWin /KWin activeWindow 2>/dev/null >/dev/null && echo "")
  cap=$(qdbus org.kde.KWin /KWin 2>/dev/null | grep -c . )
  echo "  $(date +%H:%M:%S.%N | cut -c1-12) active=$w"
  sleep 0.4
done

echo
echo '== KWin 支持的 DBus 方法（找找有没有窗口列表相关）'
qdbus org.kde.KWin /KWin 2>/dev/null | head -20
