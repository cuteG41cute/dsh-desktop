"""用一个假的 gi 模块，静态验证 dsh_manager.gui 的导入与类定义不会炸。

真实 GTK 跑不在这里（宿主是 Windows），但这一步能抓到：
导入错误、语法问题、模块级未定义名、类定义时（例如继承 Gtk.MenuButton）的明显错误。
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # manager/ 目录（里面才是 dsh_manager 包）


def _method(*a, **k):
    return None


class _DummyMeta(type):
    """让 Gtk.MenuButton / Gtk.ProgressBar 这类名字随取随有，并且是真类（可被继承）。"""

    def __getattr__(cls, item):
        if item.startswith('__'):
            raise AttributeError(item)
        if item[:1].isupper():
            return _DummyMeta(item, (_DummyBase,), {})
        return _method


class _DummyBase(object, metaclass=_DummyMeta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, item):
        if item.startswith('__'):
            raise AttributeError(item)
        return _method


class _AutoModule(types.ModuleType):
    def __getattr__(self, item):
        if item.startswith('__'):
            raise AttributeError(item)
        if item[:1].isupper():
            return _DummyMeta(item, (_DummyBase,), {})
        return _method


gi = types.ModuleType('gi')
gi.require_version = lambda *a, **k: None
repository = _AutoModule('gi.repository')
gi.repository = repository
sys.modules['gi'] = gi
sys.modules['gi.repository'] = repository

sys.path.insert(0, ROOT)
from dsh_manager import gui  # noqa: E402
from dsh_manager import core  # noqa: E402

checks = []
for name in ('VersionPicker', 'make_pulse_bar', 'pulse_until', 'ManagerWindow'):
    checks.append((name, hasattr(gui, name)))
for meth in ('_busy_show', '_busy_hide', '_busy_pulse', 'on_new', 'on_update'):
    checks.append(('ManagerWindow.' + meth, hasattr(gui.ManagerWindow, meth)))
for name in ('latest_dsh_version', 'latest_node_version', '_registry_versions'):
    checks.append(('Manager.' + name, hasattr(core.Manager, name)))
checks.append(('core._semver_key', hasattr(core, '_semver_key')))
# 排序语义：rc.5 > rc.4，正式版 > 同号预发布
checks.append(('semver rc.5 > rc.4', core._semver_key('0.2.1-rc.5') > core._semver_key('0.2.1-rc.4')))
checks.append(('semver 0.2.1 > rc.9', core._semver_key('0.2.1') > core._semver_key('0.2.1-rc.9')))

# 回归断言：gui.py 里 Gdk 的 require_version 必须出现在 import 之前
# （GTK4 也提供 Gdk，漏写就会 Requiring namespace 'Gtk' version '3.0', but '4.0' is already loaded）
src = open(os.path.join(ROOT, 'dsh_manager', 'gui.py'), encoding='utf-8').read()
req_at = src.find("require_version('Gdk'")
imp_at = src.find('from gi.repository import Gdk')
checks.append(('Gdk 版本声明在 import 之前', 0 <= req_at < imp_at))
checks.append(('声明的是 Gdk 3.0', "require_version('Gdk', '3.0')" in src))

bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(('  OK  ' if ok else '  FAIL ') + n)
print('RESULT: ' + ('FAIL ' + ','.join(bad) if bad else 'PASS %d/%d' % (len(checks), len(checks))))
sys.exit(1 if bad else 0)
