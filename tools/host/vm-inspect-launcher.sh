#!/bin/bash
# 看桌面启动脚本怎么找 node，并确认实例自带的 node 路径。
set -u
SH="$HOME/Program/deepseek-harness-1/share/dsh-desktop"
echo "== $SH"
sed -n '1,80p' "$SH"
echo '== 自带 node'
ls -l "$HOME/Program/deepseek-harness-1/node/bin/" 2>/dev/null | head
echo '== 实例 2'
ls -l "$HOME/.local/opt/deepseek-harness-2/node/bin/" 2>/dev/null | head
echo '== 桌面会话里的 node'
pgrep -af 'dsh|node' | grep -v pgrep | head -10
