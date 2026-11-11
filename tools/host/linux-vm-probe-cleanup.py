#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '/usr/lib/dsh-manager')
import dsh_manager.core as core

print('has _rmtree_force:', hasattr(core, '_rmtree_force'))
print('has _port_listening:', hasattr(core, '_port_listening'))

p = '/tmp/rmtree-probe'
core._rmtree_force(p)
os.makedirs(os.path.join(p, 'a'), exist_ok=True)
print('probe before:', os.path.exists(p))
core._rmtree_force(p)
print('probe after:', os.path.exists(p))

p2 = '/tmp/inst-fail-probe'
core._rmtree_force(p2)
m = core.Manager()
m._install_node = lambda inst, v: None
m._npm_install = lambda inst, v: (_ for _ in ()).throw(RuntimeError('boom'))
ok, msg, inst = m.install(p2, '9.9.9', '9.9.9', 3989, 'fail')
print('install ok:', ok)
print('prefix:', inst.prefix if inst else None)
print('exists after:', os.path.exists(p2))
print('--- manager.log tail ---')
try:
    tail = open(os.path.join(os.path.dirname(core.settings_path()), 'manager.log'), encoding='utf-8').read().strip().splitlines()[-8:]
    print('\n'.join(tail))
except OSError as exc:
    print('no log', exc)
