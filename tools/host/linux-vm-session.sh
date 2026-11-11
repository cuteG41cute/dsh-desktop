#!/bin/bash
# 装新包 → 杀掉旧窗口进程 → 重新 open → 检查注入日志
set -u
PREFIX=/home/twinblade/.local/opt/deepseek-harness-2
sudo -n dpkg -i /tmp/dsh-manager.deb >/dev/null 2>&1 || true
echo "版本: $(dpkg-query -W -f='${Version}' dsh-manager)"

src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

# 关掉旧窗口进程（否则 open 只是把它提到前台）
pkill -f "share/dsh-desktop" 2>/dev/null || true
sleep 2
: > "$PREFIX/logs/desktop.log" 2>/dev/null || true

dsh-manager --headless open --prefix "$PREFIX" 2>&1 | tail -2
sleep 10

echo "=== 注入日志 ==="
grep -a "injected" "$PREFIX/logs/desktop.log" 2>/dev/null | tail -8 || echo "(没有 injected 行)"
echo "=== 窗口 ==="
xdotool search --name "DeepSeek" 2>/dev/null | head -5 | while read -r w; do
  echo "  id=$w [$(xdotool getwindowname "$w" 2>/dev/null)]"
done
id=$(xdotool search --name "DeepSeek" 2>/dev/null | head -1)
if [ -n "${id:-}" ]; then
  xdotool windowactivate "$id"; sleep 2
  import -window "$id" /tmp/shot-session.png
  echo "session shot=$(ls -l /tmp/shot-session.png 2>/dev/null | awk '{print $5}')"
fi
