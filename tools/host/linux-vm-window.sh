#!/bin/bash
# 启动 VM 上的实例并打开窗口，检查注入脚本是否生效
set -u
PREFIX=/home/twinblade/.local/opt/deepseek-harness-2
echo "=== list ==="
dsh-manager --headless list 2>&1 | head -6

echo "=== start ==="
dsh-manager --headless start --prefix "$PREFIX" 2>&1 | tail -3
sleep 3
echo "=== status ==="
dsh-manager --headless status --prefix "$PREFIX" 2>&1 | tail -2

echo "=== open window ==="
src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")

dsh-manager --headless open --prefix "$PREFIX" 2>&1 | tail -2
sleep 8

echo "=== 窗口 ==="
xdotool search --onlyvisible --name "" 2>/dev/null | head -10 | while read -r w; do
  echo "  $w [$(xdotool getwindowname "$w" 2>/dev/null)]"
done

echo "=== 注入日志（stderr 落到 ~/.config/dsh-manager/ 或 journal）==="
grep -a "injected" ~/.config/dsh-manager/*.log 2>/dev/null | tail -8 || true
journalctl --user -n 40 --no-pager 2>/dev/null | grep -a "injected" | tail -8 || true
