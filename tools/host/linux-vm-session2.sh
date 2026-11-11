#!/bin/bash
# 装包 → 铺 share/web → 用 X11 后端重开窗口 → 检查注入 + 截图
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
export GDK_BACKEND=x11

pkill -f "share/dsh-desktop" 2>/dev/null || true
sleep 2
: > "$PREFIX/logs/desktop.log" 2>/dev/null || true

echo "=== open（X11 后端）==="
dsh-manager --headless open --prefix "$PREFIX" 2>&1 | tail -2
sleep 10

echo "=== share/web ==="
ls "$PREFIX/share/web" 2>/dev/null | tr '\n' ' '; echo
echo "=== 新版 dsh-desktop.py? ==="
grep -c "load_web_scripts" "$PREFIX/share/dsh-desktop.py" 2>/dev/null || echo 0

echo "=== 注入日志 ==="
grep -a "injected" "$PREFIX/logs/desktop.log" 2>/dev/null | tail -8 || echo "(无 injected 行)"

echo "=== 窗口 ==="
xdotool search --onlyvisible --name "" 2>/dev/null | head -12 | while read -r w; do
  echo "  id=$w name=[$(xdotool getwindowname "$w" 2>/dev/null)]"
done
id=$(xdotool search --name "DeepSeek Harness" 2>/dev/null | grep -v 18874376 | head -1)
if [ -n "${id:-}" ]; then
  xdotool windowactivate "$id"; sleep 2
  import -window "$id" /tmp/shot-session.png
  echo "session shot=$(ls -l /tmp/shot-session.png 2>/dev/null | awk '{print $5}')"
fi
