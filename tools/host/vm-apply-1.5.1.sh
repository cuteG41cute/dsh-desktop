#!/bin/bash
# 装 1.5.1 管理器，然后用它自己更新 dsh-memory-db 到 0.6.2（走代理），最后重启实例与管理器。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export http_proxy=http://172.22.144.1:7891
export https_proxy=$http_proxy
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$http_proxy
export no_proxy=localhost,127.0.0.1,::1,172.22.144.1,172.22.148.197,.local
export NO_PROXY=$no_proxy

P1="$HOME/Program/deepseek-harness-1"
DEB=/home/twinblade/dsh-build/linux/manager/dsh-manager_1.5.1_all.deb

echo '== 1. 装 1.5.1'
ls -l "$DEB" || exit 1
sudo dpkg -i "$DEB" 2>&1 | tail -3
grep -n "MANAGER_VERSION" /usr/lib/dsh-manager/dsh_manager/core.py | head -2

echo
echo '== 2. 让当前 systemd user 会话也带上代理（GUI 新起的进程立刻生效）'
systemctl --user set-environment http_proxy="$http_proxy" https_proxy="$https_proxy" \
  HTTP_PROXY="$http_proxy" HTTPS_PROXY="$https_proxy" no_proxy="$no_proxy" NO_PROXY="$no_proxy" \
  && echo '  systemd user 环境已更新' || echo '  systemd user 更新失败（不影响已写入的 environment.d）'

echo
echo '== 3. 用管理器自己的代码更新 dsh-memory-db'
PREFIX="$P1" python3 /tmp/vm-update-plugin.py

echo
echo '== 4. 重启实例 1（插件要重启服务才生效）'
dsh-manager --headless stop  --prefix "$P1" 2>&1 | tail -2
sleep 2
dsh-manager --headless start --prefix "$P1" 2>&1 | tail -3
sleep 8
dsh-manager --headless status --prefix "$P1" 2>&1 | tail -5

echo
echo '== 5. 重启管理器 GUI（让它在带代理的环境里跑起来）'
pkill -f '/usr/bin/dsh-manager' 2>/dev/null
sleep 1
W=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
setsid nohup env XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus" \
  http_proxy="$http_proxy" https_proxy="$https_proxy" \
  no_proxy="$no_proxy" HOME="$HOME" \
  /usr/bin/dsh-manager >>/tmp/dsh-manager-new.log 2>&1 &
sleep 6
pgrep -af '/usr/bin/dsh-manager' | head -3 || echo '  （管理器没起来，见 /tmp/dsh-manager-new.log）'

echo
echo '== 6. 复查：部署副本 + 日志'
python3 - "$P1" <<'PY'
import json, os, sys
p = os.path.join(sys.argv[1], 'dsh-home/profiles/web/node_modules/dsh-memory-db/package.json')
raw = open(p, 'rb').read()
print('  前 3 字节:', raw[:3])
d = json.loads(raw.decode('utf-8-sig'))
print('  version =', d.get('version'))
PY
grep -c 'producer-owned' "$P1"/logs/web.log 2>/dev/null | sed 's/^/  web.log 里 producer-owned 行数: /'
