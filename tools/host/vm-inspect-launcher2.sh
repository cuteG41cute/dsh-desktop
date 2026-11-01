#!/bin/bash
# 看启动器怎么找 dsh 入口，然后给出正确的启动方式。
set -u
SH="$HOME/Program/deepseek-harness-1/share/dsh-desktop"
echo '== 找 dsh 的部分'
grep -n -A3 -B3 -e 'DSH_BIN' -e 'bin.js' -e 'find_dsh' "$SH" | head -60
echo '== 实例里真实的 bin.js'
ls -l "$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai/dsh/lib/bin.js" 2>/dev/null
echo '== 桌面 .desktop 文件怎么启动它'
grep -rn -e 'dsh-desktop' -e 'DSH_BIN' "$HOME/.local/share/applications"/*.desktop 2>/dev/null | head -10
