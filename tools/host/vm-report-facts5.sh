#!/bin/bash
# 报告里要引用的细节：memory-db 版本、三处 source 的上下文、PLUGIN 常量
set -u
export HOME=/home/twinblade
N="$HOME/Program/deepseek-harness-1/dsh-home/profiles/web/node_modules"

echo '== memory-db 版本（按 utf-8-sig 读，因为文件带 BOM）'
python3 - "$N/dsh-memory-db/package.json" <<'PY'
import json, sys
p = sys.argv[1]
raw = open(p, 'rb').read()
print('  前 3 字节:', raw[:3])
d = json.loads(raw.decode('utf-8-sig'))
print('  name=%s version=%s' % (d.get('name'), d.get('version')))
print('  dsh 依赖声明:', json.dumps(d.get('dsh'), ensure_ascii=False)[:200])
PY

echo
echo '== memory-db 3118-3170（4 处的后 3 处上下文）'
sed -n '3118,3170p' "$N/dsh-memory-db/lib/index.js"

echo
echo '== PLUGIN 常量'
grep -n "const PLUGIN" "$N/dsh-memory-db/lib/index.js" "$N/dsh-time-stamp/lib/index.js" "$N/dsh-api/lib/core.js" | head -6

echo
echo '== dsh-api 上下文（236-250）'
sed -n '236,250p' "$N/dsh-api/lib/core.js"

echo
echo '== time-stamp 上下文（284-300）'
sed -n '284,300p' "$N/dsh-time-stamp/lib/index.js"

echo
echo '== 三个插件的 package.json 版本'
for p in dsh-memory-db dsh-api dsh-time-stamp; do
  python3 - "$N/$p/package.json" <<'PY'
import json, sys
p = sys.argv[1]
raw = open(p, 'rb').read()
d = json.loads(raw.decode('utf-8-sig'))
print('  %-16s v%s' % (d.get('name'), d.get('version')))
PY
done
