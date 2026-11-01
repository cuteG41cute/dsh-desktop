#!/bin/bash
# Deploy the aligned manager to the VM: sync source of truth, rebuild the deb, install it,
# then restart the manager so the user sees the new build immediately.
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
export XAUTHORITY=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
export LIBGL_ALWAYS_SOFTWARE=1

SRC="$HOME/dsh-build/linux/manager"
rm -rf "$HOME/dsh-dev"; mkdir -p "$HOME/dsh-dev"
tar -xzf /tmp/manager-dev.tgz -C "$HOME/dsh-dev" || { echo "unpack failed"; exit 1; }

echo "== sync source of truth: $SRC"
cp -a "$HOME/dsh-dev/dsh_manager/." "$SRC/dsh_manager/"
# build-deb.sh 也要同步：包里要带 icons/*.png（鲸鱼图），只拷 dsh_manager 会漏
if [ -f "$HOME/dsh-dev/build-deb.sh" ]; then cp -a "$HOME/dsh-dev/build-deb.sh" "$SRC/build-deb.sh"; fi
V=$(grep -o "MANAGER_VERSION = '[^']*'" "$SRC/dsh_manager/core.py" | head -1 | cut -d"'" -f2)
echo "   version now: $V"

echo "== build deb"
cd "$SRC" || exit 1
sed -i "s/^VERSION=.*/VERSION=\"$V\"/" build-deb.sh
rm -f "dsh-manager_${V}_all.deb"
bash build-deb.sh --version "$V" 2>&1 | tail -5
ls -la "dsh-manager_${V}_all.deb" 2>/dev/null || { echo "deb missing"; exit 1; }

echo "== install"
sudo -n dpkg -i "dsh-manager_${V}_all.deb" 2>&1 | tail -5
dpkg -l dsh-manager | tail -n +6

echo "== restart manager"
pkill -f "/usr/bin/python3 /usr/bin/dsh-manager" 2>/dev/null
pkill -f "bin/dsh-manager" 2>/dev/null
sleep 1
setsid nohup /usr/bin/dsh-manager >> /tmp/dsh-manager.log 2>&1 < /dev/null &
sleep 8
ps -eo pid,etimes,cmd | grep -E "dsh-manager" | grep -v grep | head -5
tail -5 /tmp/dsh-manager.log

echo "== screenshot"
python3 /tmp/vm-shot.py /tmp/align/after.png portal 2>&1 | tail -3
