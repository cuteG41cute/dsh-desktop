#!/bin/bash
# 部署 DBus 版剪贴板脚本并单独验证（不再轮询 Wayland）。
set -u
export HOME=/home/twinblade
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
K="org.kde.klipper.klipper"
D="$HOME/.local/share/dsh-clip"
mkdir -p "$D"
cp -f /tmp/vm-watch.py /tmp/vm-apply.py "$D"/
chmod +x "$D"/*.py
ls -l "$D"
pkill -f 'vm-watch.py' 2>/dev/null
pkill -f 'vm-apply.py' 2>/dev/null
sleep 0.5

echo '== 1. vm-apply 写一行 -> Klipper 读到'
printf '%s %s\n' abc123 "$(printf 'apply 自检 A' | base64 -w0)" | timeout 20 python3 "$D/vm-apply.py"
timeout 8 gdbus call --session --dest org.kde.klipper --object-path /klipper --method $K.getClipboardContents

echo '== 2. vm-watch 监听 -> 用 DBus 改剪贴板 -> 应打出一行'
timeout 6 python3 "$D/vm-watch.py" > /tmp/watch-out.txt 2>/tmp/watch-err.txt &
WPID=$!
sleep 1.5
timeout 8 gdbus call --session --dest org.kde.klipper --object-path /klipper --method $K.setClipboardContents "watch 自检 B 中文" >/dev/null
sleep 1.0
timeout 8 gdbus call --session --dest org.kde.klipper --object-path /klipper --method $K.setClipboardContents "watch 自检 C 第二次" >/dev/null
sleep 1.5
echo '  --- stdout（应有两行 base64）'
cat /tmp/watch-out.txt
echo '  --- stderr'
cat /tmp/watch-err.txt
wait $WPID 2>/dev/null
echo '== 3. 解码第三行看内容'
python3 - <<'PY'
import base64, io
lines = io.open('/tmp/watch-out.txt', encoding='utf-8').read().strip().splitlines()
for ln in lines[-2:]:
    if ' ' in ln:
        d, b = ln.split(' ', 1)
        print('  ', d[:8], '->', base64.b64decode(b).decode('utf-8'))
PY
echo '== 完成'
