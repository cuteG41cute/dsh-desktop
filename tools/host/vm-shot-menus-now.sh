#!/bin/bash
# 现在虚拟机桌面长什么样（看看是不是有卡住的菜单/弹窗/窗口）。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade
kscreen-doctor --dpms on >/dev/null 2>&1
sleep 1
python3 /tmp/vm-shot.py /tmp/menus-now.png 2>&1 | tail -1
echo '== 当前窗口列表（X 侧能看到的）'
DISPLAY=:1 XAUTHORITY=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1) xdotool search --onlyvisible --name '.' getwindowname %@ 2>/dev/null | grep -v '^$' | head -12
echo '== plasmashell / kwin 状态'
ps -o pid,nlwp,pcpu,stat,cmd -p $(pgrep -d, plasmashell 2>/dev/null),$(pgrep -d, kwin_wayland 2>/dev/null) 2>/dev/null
