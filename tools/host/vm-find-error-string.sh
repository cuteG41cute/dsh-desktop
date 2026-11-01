#!/bin/bash
# 找 "format v4 message requires a producer-owned source kind" 这句是在哪个包里抛的。
set -u
export HOME=/home/twinblade
for root in "$HOME/Program/deepseek-harness-1" "$HOME/.local/opt/deepseek-harness-2"; do
  echo "===== $root"
  [ -d "$root" ] || { echo '  (missing)'; break; }
  grep -rl --include='*.js' --include='*.mjs' --include='*.cjs' --include='*.ts' -e 'producer-owned' "$root" 2>/dev/null | head -10
  echo '  -- format v4:'
  grep -rl --include='*.js' --include='*.mjs' -e 'format v4' "$root" 2>/dev/null | head -10
  echo '  -- source kind:'
  grep -rl --include='*.js' --include='*.mjs' -e 'source kind' -e 'sourceKind' "$root" 2>/dev/null | head -10
done
echo '===== 版本'
grep -o '"version": *"[^"]*"' "$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai/dsh/package.json" 2>/dev/null | head -2
grep -o '"version": *"[^"]*"' "$HOME/.local/opt/deepseek-harness-2/app/node_modules/@deepseek-ai/dsh/package.json" 2>/dev/null | head -2
