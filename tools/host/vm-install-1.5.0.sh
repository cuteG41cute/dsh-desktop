#!/bin/bash
# 装上 1.5.0，把新窗口文件同步到两个实例的 share/，重启桌面窗口并截图确认。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade
XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
[ -n "${XA:-}" ] && export XAUTHORITY="$XA"
unset DISPLAY GDK_BACKEND

DEB=/home/twinblade/dsh-build/linux/manager/dsh-manager_1.5.0_all.deb
echo '== 包内关键文件'
dpkg-deb --contents "$DEB" | grep -E 'share/(dsh-desktop\.py|preview-tools\.js)$'
echo '== 安装'
sudo dpkg -i "$DEB" 2>&1 | tail -5
echo '== 自检'
/usr/lib/dsh-manager/share/dsh-desktop.py --selftest 2>&1 | tail -15 || true
echo '== 同步到实例 share/'
for d in "$HOME/Program/deepseek-harness-1/share" "$HOME/.local/opt/deepseek-harness-2/share"; do
  if [ -d "$d" ]; then
    cp -f /usr/lib/dsh-manager/share/dsh-desktop.py "$d/dsh-desktop.py"
    echo "$d/dsh-desktop.py  $(stat -c%s "$d/dsh-desktop.py") bytes  POPUP_JS=$(grep -c 'POPUP_JS' "$d/dsh-desktop.py")"
  fi
done
echo '== 重启桌面窗口'
pkill -f 'dsh-desktop.py http://127.0.0.1:3080' 2>/dev/null
pkill -f 'share/dsh-desktop$' 2>/dev/null
sleep 2
kscreen-doctor --dpms on >/dev/null 2>&1
: > /tmp/dsh-desktop-live.log
setsid nohup bash "$HOME/Program/deepseek-harness-1/share/dsh-desktop" >>/tmp/dsh-desktop-live.log 2>&1 &
sleep 10
echo '== 进程'
pgrep -af 'dsh-desktop' | grep -v pgrep | head -5
echo '== 日志'
grep -v -e DeprecationWarning -e '^  ' /tmp/dsh-desktop-live.log | head -20
echo '== 截图'
python3 /tmp/vm-shot.py /tmp/after-install.png 2>&1 | tail -1
