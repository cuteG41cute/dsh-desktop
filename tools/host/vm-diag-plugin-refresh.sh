#!/bin/bash
# 确认两件事：1) 部署副本的真实版本（带 BOM，json.load 会失败）2) 管理器缓存里还是旧 tarball
set -u
export HOME=/home/twinblade
P="$HOME/Program/deepseek-harness-1"
N="$P/dsh-home/profiles/web/node_modules"

echo '== 1. 部署副本版本（utf-8-sig 读）'
python3 - "$N/dsh-memory-db/package.json" <<'PY'
import json, sys
raw = open(sys.argv[1], 'rb').read()
print('  前 3 字节:', raw[:3])
try:
    d = json.loads(raw.decode('utf-8'))
    print('  utf-8 读: OK version=', d.get('version'))
except Exception as exc:
    print('  utf-8 读: 失败 ->', exc)
d = json.loads(raw.decode('utf-8-sig'))
print('  utf-8-sig 读: version=', d.get('version'), 'name=', d.get('name'))
PY

echo
echo '== 2. 管理器记录的安装信息（<前缀>/plugins.json）'
python3 - "$P/plugins.json" <<'PY'
import json, sys, os
p = sys.argv[1]
print('  存在:', os.path.exists(p))
if os.path.exists(p):
    d = json.load(open(p, encoding='utf-8'))
    print('  keys:', list(d.keys())[:10])
    for k, v in d.items():
        if 'memory' in k:
            print('   ', k, '->', json.dumps(v, ensure_ascii=False))
PY

echo
echo '== 3. 插件 tarball 缓存（更新会不会复用旧包）'
C="${XDG_CACHE_HOME:-$HOME/.cache}/dsh-manager/plugin-cache"
ls -lt "$C" 2>/dev/null | head -12
echo '  -- memory-db 缓存包里的版本'
TB=$(ls "$C"/dsh-memory-db-*.tar.gz 2>/dev/null | head -1)
if [ -n "${TB:-}" ]; then
  echo "  包: $TB ($(stat -c%s "$TB") bytes, mtime $(date -r "$TB" +%F' '%T)）"
  tar tzf "$TB" 2>/dev/null | grep -E 'package.json$' | head -6
  T=$(mktemp -d); tar xzf "$TB" -C "$T" 2>/dev/null
  find "$T" -name package.json -maxdepth 3 | while read -r f; do
    python3 - "$f" <<'PY'
import json, sys
raw = open(sys.argv[1], 'rb').read()
try:
    d = json.loads(raw.decode('utf-8-sig'))
    print('   ', sys.argv[1].split('/')[-2], d.get('name'), d.get('version'))
except Exception as exc:
    print('   ', sys.argv[1], '解析失败', exc)
PY
  done
  rm -rf "$T"
fi

echo
echo '== 4. GitHub 上 memory-db 的最新 release'
curl -s -H 'User-Agent: dsh-manager' https://api.github.com/repos/cuteG41cute/dsh-memory-db/releases/latest | grep -E '"tag_name"|"name"' | head -4
echo '== packages 里 memory-db 的 package.json（raw）前几个字节'
curl -s -H 'User-Agent: dsh-manager' "https://raw.githubusercontent.com/cuteG41cute/dsh-memory-db/main/static/package.json" | head -c 120 | od -c | head -3
