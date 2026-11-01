#!/bin/bash
# 看 Plasma 的剪贴板历史（klipper）配置：有没有「内容变化就弹窗」这类会抢焦点的选项。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export HOME=/home/twinblade
echo '== klipperrc'
cat "$HOME/.config/klipperrc" 2>/dev/null || echo '  （没有 klipperrc）'
echo
echo '== plasmarc 里的剪贴板相关'
grep -i -n -e clipboard -e klipper "$HOME/.config/plasmarc" 2>/dev/null | head -20 || echo '  （无）'
echo
echo '== 有没有 klipper / clipboard 相关进程'
pgrep -af -i -e klipper -e kclip | head -5 || echo '  （没有）'
echo
echo '== 桌面上正在开的窗口（含标题）'
qdbus org.kde.KWin /KWin 2>/dev/null | head -3
echo '== 当前激活窗口'
DISPLAY=:1 XAUTHORITY=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1) xdotool getactivewindow getwindowname 2>/dev/null || echo '  （拿不到）'
