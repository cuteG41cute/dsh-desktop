#!/usr/bin/env python3
"""用管理器自己的插件代码，把 dsh-memory-db 更新到最新（验证 BOM + 缓存修复）。"""
import json
import os
import sys

sys.path.insert(0, '/usr/lib/dsh-manager')
from dsh_manager import core, plugins  # noqa: E402

prefix = os.environ.get('PREFIX', os.path.expanduser('~/Program/deepseek-harness-1'))
meta = {}
try:
    with open(os.path.join(prefix, 'install.json'), 'r', encoding='utf-8') as fh:
        meta = json.load(fh)
except Exception as exc:
    print('读 install.json 失败：%s' % exc)
inst = core.Instance(prefix, meta)

pid = 'dsh-memory-db'
print('== 环境')
print('  prefix =', prefix)
print('  已装版本（修 BOM 前这里是空的）=', plugins.package_version(inst, pid) or '(读不到)')

entry = plugins.find(pid)
print('== 目录条目')
print('  ', {k: entry.get(k) for k in ('id', 'repo', 'subdir', 'name')} if entry else None)
if not entry:
    raise SystemExit('内置目录里没有 %s，无法更新' % pid)

print('== 开始更新（会强制重新下载，不再用旧缓存）')
ok, msg = plugins.install(inst, entry, log=lambda s: print('  [install]', s))
print('  结果:', ok, '|', msg)

ver = plugins.package_version(inst, pid)
print('== 更新后版本 =', ver or '(仍读不到)')
pkg = os.path.join(plugins.node_modules(inst), pid, 'package.json')
raw = open(pkg, 'rb').read()
print('  package.json 前 3 字节:', raw[:3], '(带 BOM 的话是 b\'\\xef\\xbb\\xbf\')')
print('  source.kind 形态:')
lib = os.path.join(plugins.node_modules(inst), pid, 'lib', 'index.js')
try:
    text = open(lib, 'r', encoding='utf-8', errors='replace').read()
    print('    旧形态 kind: \'plugin\', 出现', text.count("kind: 'plugin',"), '处')
    print('    新形态 plugin:', text.count("kind: 'plugin:'"), '处')
except Exception as exc:
    print('    读 lib/index.js 失败：%s' % exc)
