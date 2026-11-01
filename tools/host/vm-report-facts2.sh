#!/bin/bash
# 最后几个事实：0.2.1 客户端怎么认 plugin 源、0.1.5 有没有把 kind='plugin' 当特例、
# 管理器 CLI 的启停命令、会话文件在哪。
set -u
export HOME=/home/twinblade
A="$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai"

echo '== A. 0.2.1 客户端 / 会话层是否特判 kind === "plugin"'
grep -rn --include='*.js' -e "kind === 'plugin'" -e 'kind === "plugin"' "$A" 2>/dev/null | grep -v experimental-inspector | head -12

echo
echo '== B. 0.2.1 里 plugin 源的渲染/归属线索（form / sections / plugin: 前缀）'
grep -rn --include='*.js' -e "startsWith('plugin:'" -e 'startsWith("plugin:' "$A" 2>/dev/null | head -8
grep -rn --include='*.js' -e "'plugin:'" "$A/dsh-session/lib" 2>/dev/null | head -5

echo
echo '== C. 管理器 CLI：怎么启停实例'
dsh-manager --headless --help 2>&1 | head -30 || dsh-manager --help 2>&1 | head -30

echo
echo '== D. 会话文件位置（jsonl）'
find "$HOME/Program/deepseek-harness-1/dsh-home" -maxdepth 3 -type d -name 'sessions' 2>/dev/null | head -3
ls "$HOME/Program/deepseek-harness-1/dsh-home" 2>/dev/null | head -10

echo
echo '== E. 会话里的 source 长什么样（找一条 plugin 注入的）'
S=$(find "$HOME/Program/deepseek-harness-1/dsh-home" -type f -name '*.jsonl' 2>/dev/null | head -1)
echo "  样本: $S"
[ -n "$S" ] && grep -o '"source":{[^}]*}' "$S" 2>/dev/null | sort | uniq -c | sort -rn | head -8
