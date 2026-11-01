#!/bin/bash
# 看清三处 V3 源的写法，以及 0.2.1 的 userMessage() 第二个参数是什么。
set -u
export HOME=/home/twinblade
P="$HOME/Program/deepseek-harness-1/dsh-home/profiles/web/node_modules"
A="$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai"

echo '== dsh-time-stamp'
sed -n '282,298p' "$P/dsh-time-stamp/lib/index.js"
echo '== dsh-api'
sed -n '238,250p' "$P/dsh-api/lib/core.js"
echo '== dsh-memory-db（第一处）'
sed -n '2340,2352p' "$P/dsh-memory-db/lib/index.js"

echo '== 0.2.1 里 userMessage 的定义（source 参数？）'
grep -rn --include='*.js' -e 'function userMessage' "$A" 2>/dev/null | head -5
for f in $(grep -rl --include='*.js' -e 'function userMessage' "$A" 2>/dev/null | head -2); do
  echo "--- $f"
  grep -n -A12 'function userMessage' "$f" | head -20
done

echo '== dsh-memory-db 的 manifest 有没有 BOM'
head -c 8 "$P/dsh-memory-db/package.json" | od -c | head -2
python3 - <<'PY'
import json, os
p = os.path.expanduser('~/Program/deepseek-harness-1/dsh-home/profiles/web/node_modules/dsh-memory-db/package.json')
raw = open(p, 'rb').read()
print('  前 3 字节:', raw[:3])
try:
    json.loads(raw.decode('utf-8-sig'))
    print('  去掉 BOM 后能解析')
except Exception as exc:
    print('  解析失败:', exc)
PY
