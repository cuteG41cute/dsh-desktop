#!/bin/bash
# 关键：插件内部除了「写 source」，还有「读 source」的地方（去重/判定），也必须一起改。
set -u
export HOME=/home/twinblade
N="$HOME/Program/deepseek-harness-1/dsh-home/profiles/web/node_modules"
for p in dsh-memory-db dsh-api dsh-time-stamp; do
  echo "===== $p"
  grep -rn --include='*.js' -e "source\.plugin" -e "source\.kind" -e "kind === 'plugin'" -e 'kind === "plugin"' "$N/$p" 2>/dev/null | sed "s|$N/||" | head -20
done

echo
echo '== memory-db: lastInjectedText / previousUserMessageTime 怎么判定自己注入的消息'
grep -n -A10 'function lastInjectedText' "$N/dsh-memory-db/lib/index.js" | head -18
grep -n -A12 'previousUserMessageTime' "$N/dsh-time-stamp/lib/index.js" | head -24
