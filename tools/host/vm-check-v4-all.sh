#!/bin/bash
# 1) 所有已装插件里谁在用 V3 的 plugin 源；2) memory-db 现在是否启用；3) 0.2.1 里允许的 kind 名单与客户端渲染
set -u
export HOME=/home/twinblade
A="$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai"

echo '== 1. 各实例已装插件里的 kind: plugin'
for p in "$HOME/Program/deepseek-harness-1" "$HOME/.local/opt/deepseek-harness-2"; do
  echo "--- $p"
  grep -rn --include='*.js' "kind: 'plugin'" "$p/dsh-home/profiles/web/node_modules" 2>/dev/null \
    | sed "s|$p/||" | head -12
done

echo
echo '== 2. memory-db 的行配置（是否启用）'
for p in "$HOME/Program/deepseek-harness-1" "$HOME/.local/opt/deepseek-harness-2"; do
  echo "--- $p"
  ls "$p/dsh-home/profiles/web/" 2>/dev/null
  grep -rn -A3 'memory-db' "$p/dsh-home/profiles/web/cordis.yml" 2>/dev/null | head -12
done

echo
echo '== 3. 0.2.1 允许的 source kind（RELEASED_SAME_NAME_PRODUCERS 头几项）'
sed -n '1,60p' "$A/dsh-session-format-v3-to-v4/lib/index.js"

echo
echo '== 4. 客户端如何识别「注入」来源'
grep -rn --include='*.js' -e "source.kind" -e 'source\.kind' "$A/dsh-client-ui-chat/lib/client.js" 2>/dev/null | head -10
grep -rn --include='*.js' -e "'plugin:'" -e '"plugin:"' -e 'startsWith("plugin' "$A"/*/lib/client.js 2>/dev/null | head -10
