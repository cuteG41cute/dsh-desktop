#!/bin/bash
# 写报告前把剩下的事实补齐：
#  1) 0.1.5（宿主/旧实例）到底接不接受 kind='plugin:xxx'
#  2) 两个实例里三个插件的版本与行号是否一致
#  3) 报错在日志里长什么样、实例怎么重启
set -u
export HOME=/home/twinblade
A="$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai"

echo '== 1. 0.2.1 里 v4 允许的 kind 到底有没有白名单（除了 kind!="plugin" 还查什么）'
grep -rn --include='*.js' -e 'producer-owned source kind' "$A" | head -5
grep -rn --include='*.js' -e 'function source' -A8 "$A/dsh-session-format-v3-to-v4/lib/index.js" | head -20

echo
echo '== 2. 旧版本(0.1.5)有没有同样的校验：看 host 那份没有这个包，那就查 v1->v2 / v2->v3 的校验'
ls "$A" | grep -i 'session-format' | head

echo
echo '== 3. 两个实例三个插件的版本 / 行号'
for p in "$HOME/Program/deepseek-harness-1" "$HOME/.local/opt/deepseek-harness-2"; do
  echo "--- $p"
  for name in dsh-memory-db dsh-api dsh-time-stamp; do
    d="$p/dsh-home/profiles/web/node_modules/$name"
    [ -d "$d" ] || { echo "  $name: (未安装)"; continue; }
    ver=$(python3 -c "import json;print(json.load(open('$d/package.json'))['version'])" 2>/dev/null || echo '?')
    hits=$(grep -rn --include='*.js' "kind: 'plugin'" "$d" 2>/dev/null | wc -l)
    echo "  $name v$ver  kind:plugin 命中 $hits 处"
    grep -rn --include='*.js' "kind: 'plugin'" "$d" 2>/dev/null | sed "s|$d/||" | head -6
  done
done

echo
echo '== 4. 日志里这条错误的原样'
grep -rn 'producer-owned' "$HOME"/Program/deepseek-harness-1/logs/*.log 2>/dev/null | tail -3
grep -rn 'disabling profile plugin row' "$HOME"/Program/deepseek-harness-1/logs/web.log 2>/dev/null | tail -3
echo '--- 管理器的重启方式（CLI 帮助）'
command -v dsh-manager && dsh-manager --headless list 2>&1 | head -8
