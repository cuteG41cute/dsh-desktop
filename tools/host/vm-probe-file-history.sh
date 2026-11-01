#!/bin/bash
# 给 dsh-file-history 出报告前要查清的事实
set -u
export HOME=/home/twinblade
export http_proxy=http://172.22.144.1:7891
export https_proxy=$http_proxy
N="$HOME/Program/deepseek-harness-1/dsh-home/profiles/web/node_modules"
A="$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai"
F="$N/dsh-file-history"

echo '== 1. 版本 / BOM'
python3 - "$F/package.json" <<'PY'
import json, sys
raw = open(sys.argv[1], 'rb').read()
print('  前 3 字节:', raw[:3])
d = json.loads(raw.decode('utf-8-sig'))
print('  name=%s version=%s' % (d.get('name'), d.get('version')))
print('  dsh 声明:', json.dumps(d.get('dsh'), ensure_ascii=False)[:300])
print('  engines:', d.get('engines'))
PY

echo
echo '== 2. settings 接口的用法（行号）'
grep -rn --include='*.js' -e 'settings\.' "$F/lib" 2>/dev/null | sed "s|$F/||" | head -20

echo
echo '== 3. 报错点上下文（index.js:960-1000）'
sed -n '960,1000p' "$F/lib/index.js"

echo
echo '== 4. settings 命名空间 / schema 定义'
grep -rn --include='*.js' -e 'SETTINGS_NS' -e 'Schema' -e 'schema' "$F/lib/index.js" | head -15

echo
echo '== 5. 0.2.1 里 settings 服务的公开方法'
S="$A/dsh-settings/lib/types/index.d.ts"
ls -l "$S" 2>/dev/null
grep -nE '^\s{2,}(configure|update|replace|mutate|describe|get|register|writable|prepareDocument|documentPath)' "$S" 2>/dev/null | head -20
echo '  -- 服务类里所有方法名'
grep -oE '^\s+[a-zA-Z]+\(' "$S" 2>/dev/null | tr -d ' (' | sort -u | head -30

echo
echo '== 6. memory-db 是怎么绕过 settings 的（可参考的现成做法）'
grep -n -B3 -A12 'settings.register/get unavailable' "$N/dsh-memory-db/lib/index.js" | head -30

echo
echo '== 7. GitHub 上有没有更新的 file-history'
curl -s -H 'User-Agent: dsh-manager' https://api.github.com/repos/cuteG41cute/dsh-file-history/releases/latest \
  | grep -E '"tag_name"' | head -2
curl -s -H 'User-Agent: dsh-manager' https://raw.githubusercontent.com/cuteG41cute/dsh-file-history/main/package.json \
  | grep -E '"version"' | head -2
