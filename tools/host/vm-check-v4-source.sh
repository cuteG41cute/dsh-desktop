#!/bin/bash
# 确认：虚拟机里哪个插件在用 V3 的 source.kind='plugin'，以及 0.2.1 要求什么形状。
set -u
export HOME=/home/twinblade
A="$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai"
B="$HOME/.local/opt/deepseek-harness-2/app/node_modules/@deepseek-ai"

echo '== 1. 两个实例装的 memory-db 版本'
for p in "$HOME/Program/deepseek-harness-1" "$HOME/.local/opt/deepseek-harness-2"; do
  for d in "$p/dsh-home/profiles/web/node_modules/dsh-memory-db" "$p/app/node_modules/dsh-memory-db"; do
    [ -d "$d" ] || continue
    echo "$d -> $(python3 -c "import json;print(json.load(open('$d/package.json'))['version'])" 2>/dev/null || echo '?')"
  done
done

echo '== 2. 部署副本里还有没有 kind: plugin'
for p in "$HOME/Program/deepseek-harness-1" "$HOME/.local/opt/deepseek-harness-2"; do
  grep -rn --include='*.js' "kind: 'plugin'" "$p/dsh-home/profiles/web/node_modules/dsh-memory-db" 2>/dev/null | head -8
done

echo '== 3. 0.2.1 的 V4 迁移怎么映射 plugin 源'
sed -n '60,120p' "$A/dsh-session-format-v3-to-v4/lib/index.js"

echo '== 4. 客户端怎么识别 plugin 源（是不是认 kind 前缀）'
grep -rn --include='*.js' -e "startsWith('plugin:'" -e '"plugin:"' -e "kind === 'plugin'" "$A/dsh-client-ui-chat/lib/client.js" 2>/dev/null | head -8
grep -rn --include='*.js' -e "plugin:" "$A/dsh-session-format/lib/index.js" 2>/dev/null | head -8
