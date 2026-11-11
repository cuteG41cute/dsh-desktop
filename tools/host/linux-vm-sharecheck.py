#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '/usr/lib/dsh-manager')
import dsh_manager.core as core

print('SYSTEM_SHARE:', core.SYSTEM_SHARE)
print('system share/web:', sorted(os.listdir(os.path.join(core.SYSTEM_SHARE, 'web'))) if os.path.isdir(os.path.join(core.SYSTEM_SHARE, 'web')) else 'MISSING')

mgr = core.Manager()
inst = mgr.instance_at('/home/twinblade/.local/opt/deepseek-harness-2')
print('inst:', inst.prefix)
print('inst.share:', inst.share)
print('inst.share/web:', sorted(os.listdir(os.path.join(inst.share, 'web'))) if os.path.isdir(os.path.join(inst.share, 'web')) else 'MISSING')
print('dsh-desktop.py has load_web_scripts:',
      'load_web_scripts' in open(os.path.join(inst.share, 'dsh-desktop.py'), encoding='utf-8').read())
print('has _refresh_share_if_stale:', hasattr(mgr, '_refresh_share_if_stale'))
try:
    changed = mgr._refresh_share_if_stale(inst)
    print('refresh ->', changed)
except Exception as exc:
    print('refresh failed:', exc)
print('after: share/web =', sorted(os.listdir(os.path.join(inst.share, 'web'))) if os.path.isdir(os.path.join(inst.share, 'web')) else 'MISSING')
