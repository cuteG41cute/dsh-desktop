#!/bin/bash
# 收尾：杀掉端到端测试实例，用最新源码重打 deb、安装、自检。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export HOME=/home/twinblade

pkill -f 'dsh-live/dsh-desktop.py' 2>/dev/null
pkill -f 'http.server 8099' 2>/dev/null
pkill -f 'http.server 8098' 2>/dev/null
sleep 1

DEV="$HOME/dsh-build"
rm -rf "$DEV"; mkdir -p "$DEV"
tar xzf /tmp/dsh-linux.tgz -C "$DEV"
cd "$DEV/linux/manager"
bash build-deb.sh 2>&1 | grep -E '打 deb|✔|大小|sha256|警告' | head -6
DEB="$DEV/linux/manager/dsh-manager_1.5.0_all.deb"
echo '== 安装'
sudo dpkg -i "$DEB" 2>&1 | tail -3
echo '== 安装后的版本与关键标记'
grep -n "MANAGER_VERSION = " /usr/lib/dsh-manager/dsh_manager/core.py
grep -c '__dshPopupClosed' /usr/lib/dsh-manager/share/dsh-desktop.py
grep -c 'PREFIX/app/node_modules' /usr/lib/dsh-manager/share/dsh-desktop
echo '== 自检'
/usr/lib/dsh-manager/share/dsh-desktop.py --selftest 2>&1 | sed -n '1,40p'
echo '== 桌面窗口还在吗'
pgrep -af 'dsh-desktop' | grep -v pgrep | head -5
