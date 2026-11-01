#!/bin/bash
# 实例 1 现在是 stopped？查清楚并拉起来，顺便看 memory-db 这次有没有成功激活。
set -u
export HOME=/home/twinblade
P1="$HOME/Program/deepseek-harness-1"

echo '== 进程 / 端口'
pgrep -af 'dsh/lib/bin.js web' | head -3 || echo '  （没有 web 进程）'
ss -ltnp 2>/dev/null | grep -E ':3080|:3081' || echo '  （3080/3081 都没在监听）'
echo
echo '== 启动实例 1'
dsh-manager --headless start --prefix "$P1" 2>&1 | tail -3
sleep 8
dsh-manager --headless status --prefix "$P1" 2>&1 | tail -2
echo
echo '== web.log 尾部（看 memory-db 有没有激活 / 还有没有 BOM 报错）'
tail -25 "$P1/logs/web.log" 2>/dev/null
echo
echo '== 统计'
echo "  disabling profile plugin row: $(grep -c 'disabling profile plugin row' "$P1/logs/web.log" 2>/dev/null)"
echo "  producer-owned: $(grep -c 'producer-owned' "$P1/logs/web.log" 2>/dev/null)"
echo "  did not activate: $(grep -c 'did not activate' "$P1/logs/web.log" 2>/dev/null)"
