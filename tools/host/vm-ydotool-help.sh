#!/bin/bash
# 搞清楚 ydotool 这个版本的 mousemove 语法（-a 到底存不存在）。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export YDOTOOL_SOCKET=/tmp/.ydotool_socket
pgrep -x ydotoold >/dev/null || sudo bash -c 'setsid /usr/bin/ydotoold >/tmp/ydotoold.log 2>&1 &'
sleep 0.6
echo '== dpkg 版本'
dpkg -l ydotool 2>/dev/null | tail -1
echo '== ydotool help'
sudo YDOTOOL_SOCKET=$YDOTOOL_SOCKET ydotool help 2>&1 | head -25
echo '== mousemove --help'
sudo YDOTOOL_SOCKET=$YDOTOOL_SOCKET ydotool mousemove --help 2>&1 | head -15
