#!/bin/bash
# 打出报错点上下文
set -u
B="$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai"
for f in dsh-session-format-v3-to-v4/lib/index.js dsh-session/lib/types/surface.js dsh-session-format/lib/index.js; do
  echo "===== $f"
  grep -n -B6 -A18 'producer-owned' "$B/$f" 2>/dev/null | head -80
done
echo '===== 包版本'
for p in dsh-session-format-v3-to-v4 dsh-session-format dsh-session dsh; do
  printf '%-32s %s\n' "$p" "$(python3 -c "import json,sys;print(json.load(open('$B/$p/package.json'))['version'])" 2>/dev/null || echo '?')"
done
