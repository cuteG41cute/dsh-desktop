#!/bin/bash
# 拍一张当前桌面，并报告 dsh-manager 进程与窗口类名（排查"截到空白"）。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
echo "== 进程 =="
ps -eo pid,etime,cmd | grep '[d]sh-manager' | head -3
echo "== 日志尾 =="
tail -12 /tmp/dsh-manager-gui-wayland.log 2>/dev/null || echo "（无日志）"
echo "== 截图 =="
timeout 60 python3 /tmp/vm-shot.py /tmp/manager-now.png 2>&1 | tail -2
ls -l /tmp/manager-now.png 2>/dev/null
