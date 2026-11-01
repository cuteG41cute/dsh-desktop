#!/bin/bash
# 关键线索：plasmashell 是不是在反复重启/崩溃（菜单属于它，它一重启所有菜单都没了）。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export HOME=/home/twinblade

echo '== 关键进程的运行时长（elapsed 小 = 刚重启过）'
ps -o pid,etimes,pcpu,rss,cmd -C plasmashell -C kwin_wayland 2>/dev/null
echo
echo '== plasmashell 启动时刻'
ps -o pid,lstart,cmd -C plasmashell 2>/dev/null

echo
echo '== 崩溃记录（coredumpctl）'
coredumpctl list --no-pager 2>/dev/null | tail -12 || echo '  （coredumpctl 不可用）'

echo
echo '== journal 里的 crash / watchdog / segfault'
journalctl --user -b --no-pager 2>/dev/null | grep -i -E 'segfault|core-dump|watchdog|crash|kcrash|Got signal' | tail -20 || echo '  （无）'

echo
echo '== Plasma.Flex.Hub 这个 plasmoid 是什么'
ls -la "$HOME/.local/share/plasma/plasmoids/Plasma.Flex.Hub" 2>/dev/null | head
cat "$HOME/.local/share/plasma/plasmoids/Plasma.Flex.Hub/metadata.json" 2>/dev/null | head -20

echo
echo '== plasmashell 最近日志密度（每 10 秒一条算一次重启/重载）'
journalctl --user -b --no-pager 2>/dev/null | grep plasmashell | tail -30 | cut -c1-120
