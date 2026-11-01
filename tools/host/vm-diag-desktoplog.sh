#!/bin/bash
# 桌面窗口的日志：有没有反复开窗/站外导航（反复开窗会抢焦点、把菜单顶掉）。
set -u
export HOME=/home/twinblade
echo '== 实例 1 desktop.log'
cat "$HOME/Program/deepseek-harness-1/logs/desktop.log" 2>/dev/null | tail -40
echo
echo '== 有没有更多日志文件（管理器捕获窗口 stderr 的地方）'
find "$HOME/.local/state" -maxdepth 3 -name '*.log' -newermt '-6 hours' 2>/dev/null | head -10
echo
echo '== 当前所有 GUI 窗口（KWin 视角）'
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
qdbus6 org.kde.KWin /KWin org.kde.KWin.getWindowInfo 2>/dev/null | head -5
python3 - <<'PY' 2>/dev/null || true
import json, subprocess
PY
echo
echo '== wl-copy 常驻进程数量'
pgrep -c wl-copy 2>/dev/null || echo 0
