#!/bin/bash
# 验证：插件新形态、管理器看到的版本、GitHub 发现能否走代理
set -u
export HOME=/home/twinblade
export http_proxy=http://172.22.144.1:7891
export https_proxy=$http_proxy
export no_proxy=localhost,127.0.0.1,::1,172.22.144.1,.local
P1="$HOME/Program/deepseek-harness-1"

echo '== 1. 部署副本里的 source 形态'
grep -n "PLUGIN_KIND\|kind: 'plugin" "$P1/dsh-home/profiles/web/node_modules/dsh-memory-db/lib/index.js" | head -10

echo
echo '== 2. 管理器代码看到的已装版本（= 对话框「版本」列）'
python3 - "$P1" <<'PY'
import json, os, sys
sys.path.insert(0, '/usr/lib/dsh-manager')
from dsh_manager import core, plugins
prefix = sys.argv[1]
meta = json.load(open(os.path.join(prefix, 'install.json'), encoding='utf-8'))
inst = core.Instance(prefix, meta)
info = plugins.installed(inst)
for pid in ('dsh-memory-db', 'dsh-api', 'dsh-time-stamp', 'dsh-file-history', 'dsh-screenshot', 'dsh-netmon'):
    v = info.get(pid)
    if v:
        print('  %-16s 已安装=%-5s 版本=%s' % (pid, v['installed'], v['version'] or '(空)'))
PY

echo
echo '== 3. GitHub 发现（管理器用的同一段代码，走代理）'
python3 - <<'PY'
import sys
sys.path.insert(0, '/usr/lib/dsh-manager')
from dsh_manager import plugins
items = plugins.github_plugins()
print('  发现 %d 个带 dsh-plugin 标签的仓库：' % len(items))
for it in items:
    print('    %-16s %-34s 更新于 %s' % (it['id'], it['repo'], it.get('updated')))
PY

echo
echo '== 4. 实例状态'
dsh-manager --headless status --prefix "$P1" 2>&1 | tail -2
echo '== 5. 管理器 GUI 进程'
pgrep -af '/usr/bin/dsh-manager' | head -2
