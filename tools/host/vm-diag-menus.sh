#!/bin/bash
# 诊断「菜单被刷新掉」：看剪切板是不是在被反复写、有没有进程风暴、KWin/Klipper 有没有报错。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade

echo '== 剪切板 6 秒内采样（内容变了就会反复触发桌面剪贴板服务）'
prev=''
for i in $(seq 1 12); do
  v="$(timeout 3 wl-paste --no-newline 2>/dev/null | md5sum | cut -c1-8)"
  echo "  $(date +%H:%M:%S) md5=$v"
  sleep 0.5
done

echo '== 相关进程（wl-copy 常驻 / python 桥 / klipper）'
ps -eo pid,etimes,pcpu,cmd | grep -E 'wl-copy|vm-watch|vm-apply|klipper' | grep -v grep | head -20

echo '== CPU 前 5'
ps -eo pcpu,pid,etimes,comm --sort=-pcpu | head -6

echo '== KWin / plasma / klipper 日志（最近 40 条相关）'
journalctl --user -b --no-pager 2>/dev/null | grep -i -E 'klipper|clipboard|kwin_wayland|plasmashell' | tail -40 || echo '  （读不到 user journal）'

echo '== KWin 进程状态'
ps -o pid,etimes,pcpu,rss,cmd -C kwin_wayland 2>/dev/null | head -3
echo '== 会话里有多少 wayland 客户端在连'
ls /run/user/1000/wayland-* 2>/dev/null
echo '== 桌面窗口进程'
pgrep -af 'dsh-desktop' | grep -v pgrep | head -5
