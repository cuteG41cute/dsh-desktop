#!/bin/bash
# 看 DSH 桌面窗口有没有在反复加载/报错（日志里同一行反复出现 = 页面在刷新）。
set -u
export HOME=/home/twinblade
echo '== 实例 1 logs 目录'
ls -lt "$HOME/Program/deepseek-harness-1/logs" 2>/dev/null | head -8
echo '== 实例 1 web.log 尾部'
tail -20 "$HOME/Program/deepseek-harness-1/logs/web.log" 2>/dev/null
echo
echo '== 管理器状态目录（它自己也记日志）'
ls -lt "$HOME/.local/state/dsh-desktop/logs" 2>/dev/null | head -6
for f in "$HOME"/.local/state/dsh-desktop/logs/*; do
  [ -f "$f" ] || continue
  echo "--- $f ($(stat -c%s "$f") bytes)"
  tail -8 "$f"
done 2>/dev/null | head -60
echo
echo '== 桌面窗口进程的 CPU 时间（增长快 = 一直在重绘/加载）'
ps -o pid,etimes,times,pcpu,cmd -p 134011,136070 2>/dev/null
echo '== 5 秒后再看一次'
sleep 5
ps -o pid,etimes,times,pcpu,cmd -p 134011,136070 2>/dev/null
