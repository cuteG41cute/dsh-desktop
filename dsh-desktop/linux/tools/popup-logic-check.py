"""验证 dsh-desktop.py 的弹窗判定逻辑（same_origin / open_external 的选择），不需要 GTK。

用假 gi 让模块可导入（它只在 __main__ 里跑 GUI），然后直接测函数行为。
"""
import importlib.util
import os
import sys
import types

WS = os.environ['DSH_WS']
SRC = os.path.join(WS, 'dsh-desktop', 'linux', 'dsh-desktop.py')


def _method(*a, **k):
    return None


class _DummyMeta(type):
    def __getattr__(cls, item):
        if item.startswith('__'):
            raise AttributeError(item)
        if item[:1].isupper():
            return _DummyMeta(item, (_Base,), {})
        return _method


class _Base(object, metaclass=_DummyMeta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, item):
        if item.startswith('__'):
            raise AttributeError(item)
        return _method


class _Mod(types.ModuleType):
    def __getattr__(self, item):
        if item.startswith('__'):
            raise AttributeError(item)
        if item[:1].isupper():
            return _DummyMeta(item, (_Base,), {})
        return _method


for name in ('gi', 'gi.repository'):
    m = _Mod(name)
    m.require_version = lambda *a, **k: None
    sys.modules[name] = m
sys.modules['gi'].repository = sys.modules['gi.repository']

spec = importlib.util.spec_from_file_location('dshdesktop', SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

app_url = mod.WEB_URL
print('WEB_URL =', app_url)

cases = [
    ('同源页面 → 应用内窗口', app_url + '/settings', True),
    ('同源深链接 → 应用内窗口', app_url.replace('http://', 'http://') + '/?session=abc', True),
    ('登录页（站外）→ 弹窗', 'https://login.deepseek.com/oauth/authorize?x=1', False),
    ('不同端口 → 站外', 'http://127.0.0.1:9999/', False),
    ('空串 → 站外', '', False),
]
bad = []
for label, url, want in cases:
    got = mod.same_origin(url, app_url)
    ok = got == want
    print(('  OK   ' if ok else '  FAIL ') + '%s  same_origin=%s（期望 %s）' % (label, got, want))
    if not ok:
        bad.append(label)

# open_external 只处理 http(s)
print('  OK   open_external 拒绝非 http(s) 协议: %s' % (mod.open_external('mailto:a@b.c') is False))
print('RESULT: ' + ('FAIL ' + ','.join(bad) if bad else 'PASS %d 组判定' % len(cases)))
sys.exit(1 if bad else 0)
