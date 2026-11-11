#!/bin/bash
# 用「正在运行的管理器进程」的环境变量去截图（SSH 会话本身没有 DISPLAY/XAUTHORITY）
set -u
pid=$(pgrep -f '/usr/bin/dsh-manager' | head -1)
if [ -z "$pid" ]; then
  pid=$(pgrep -f 'dsh-desktop.py' | head -1)
fi
echo "pid=${pid:-none}"
if [ -n "$pid" ]; then
  echo "=== 进程环境（关键项）==="
  tr '\0' '\n' < "/proc/$pid/environ" | grep -E '^(DISPLAY|XAUTHORITY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR|XDG_SESSION_TYPE)=' || true
  DISPLAY=$(tr '\0' '\n' < "/proc/$pid/environ" | sed -n 's/^DISPLAY=//p' | head -1)
  XAUTHORITY=$(tr '\0' '\n' < "/proc/$pid/environ" | sed -n 's/^XAUTHORITY=//p' | head -1)
  XDG_RUNTIME_DIR=$(tr '\0' '\n' < "/proc/$pid/environ" | sed -n 's/^XDG_RUNTIME_DIR=//p' | head -1)
  export DISPLAY="${DISPLAY:-:0}"
  export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"
  echo "using DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY"
else
  export DISPLAY=:0
  export XAUTHORITY="$HOME/.Xauthority"
fi

echo "=== xdotool 自检 ==="
xdotool getmouselocation 2>&1 | head -1

echo "=== 窗口列表 ==="
xdotool search --name "管理器" 2>/dev/null | while read -r id; do
  name=$(xdotool getwindowname "$id" 2>/dev/null)
  echo "  id=$id name=[$name]"
done

id=$(xdotool search --name "管理器" 2>/dev/null | head -1)
if [ -n "$id" ]; then
  xdotool windowactivate "$id" 2>/dev/null || true
  sleep 1
  import -window "$id" /tmp/vm-shot.png 2>&1 | tail -2
else
  echo "WARN: 没找到管理器窗口，抓整屏"
  import -window root /tmp/vm-shot.png 2>&1 | tail -2
fi
ls -l /tmp/vm-shot.png 2>/dev/null || echo "shot failed"
