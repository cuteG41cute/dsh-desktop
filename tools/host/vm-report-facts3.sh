#!/bin/bash
# 会话文件长什么样：给报告里的「验证」一节用真实路径。
set -u
export HOME=/home/twinblade
P="$HOME/Program/deepseek-harness-1"
echo '== sessions 目录'
ls -lt "$P/dsh-home/sessions" 2>/dev/null | head -6
echo '== 找一个 jsonl'
F=$(find "$P/dsh-home/sessions" -type f \( -name '*.jsonl' -o -name '*.json' \) 2>/dev/null | head -1)
echo "  样本: ${F:-（没找到）}"
if [ -n "${F:-}" ]; then
  echo '  -- 里头的 source 形状（去重计数）'
  grep -o '"source":{[^}]*}' "$F" 2>/dev/null | sort | uniq -c | sort -rn | head -8
  echo '  -- 行数 / 大小'
  wc -l "$F" 2>/dev/null
fi
echo '== 整个 sessions 树里有没有 kind:plugin 源'
grep -rho '"kind":"plugin"' "$P/dsh-home/sessions" 2>/dev/null | wc -l
grep -rho '"kind":"plugin:[^"]*"' "$P/dsh-home/sessions" 2>/dev/null | sort | uniq -c | head -5
