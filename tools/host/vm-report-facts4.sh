#!/bin/bash
# 0.2.1 客户端怎么判定「注入行」而不是用户气泡（决定改 kind 之后的显示影响）。
set -u
export HOME=/home/twinblade
A="$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai"
echo '== 找注入/上下文相关文案与判定'
grep -rn --include='*.js' -e '上下文注入' -e 'context-injection' -e 'injection' "$A/dsh-client-ui-chat/lib/client.js" 2>/dev/null | head -8
echo '== source.kind 的全部取值判断'
grep -rho --include='*.js' -e 'source\.kind === "[^"]*"' -e "source\.kind === '[^']*'" -e 'source\.kind !== "[^"]*"' "$A" 2>/dev/null | sort | uniq -c | sort -rn | head -12
echo '== 渲染层：非 user 源怎么归类'
grep -rn --include='*.js' -e '"producer"' -e 'producerKind' -e 'plugin:' "$A/dsh-client-ui-chat/lib/client.js" 2>/dev/null | head -8
echo '== session 包对 source 的其它约束'
grep -rn --include='*.js' -e 'source' "$A/dsh-session/lib/index.js" 2>/dev/null | head -10
