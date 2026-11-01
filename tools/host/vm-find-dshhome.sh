#!/bin/bash
# 找出实例的 DSH_HOME（签 cookie 要用），并确认 mint_cookie 能签出来。
set -u
echo '== 候选目录'
for d in "$HOME/Program/deepseek-harness-1"/*/ "$HOME/Program/deepseek-harness-1"; do
  [ -d "$d" ] || continue
  echo "$d"
done | head -20
echo '== .dsh 相关内容'
find "$HOME/Program/deepseek-harness-1" -maxdepth 2 -name '*.json' -o -maxdepth 2 -name 'secrets*' -o -maxdepth 2 -type d -name 'dsh-home' 2>/dev/null | head -10
echo '== 启动器怎么设 DSH_HOME'
grep -n -e 'DSH_HOME' "$HOME/Program/deepseek-harness-1/share/dsh-desktop" | head -10
