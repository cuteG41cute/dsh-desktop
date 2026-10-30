"""用一个假的 gi 模块，静态验证 dsh_manager.gui 的导入与类定义不会炸。

真实 GTK 跑不在这里（宿主是 Windows），但这一步能抓到：
导入错误、语法问题、模块级未定义名、类定义时（例如继承 Gtk.MenuButton）的明显错误。
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # manager/ 目录（里面才是 dsh_manager 包）


class _Dummy(object):
    """万能占位对象：任何属性/调用都返回它自己（支持链式调用）。"""

    def __getattr__(self, item):
        if item.startswith('__'):
            raise AttributeError(item)
        return _method

    def __call__(self, *a, **k):
        return _Dummy()

    def __bool__(self):
        return True


def _method(*a, **k):
    return _Dummy()


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

# 结构锁：小屏上「看不到底」是因为右侧按钮组把日志挤出窗口、窗口本身又比屏幕高。
# 修法分四段，任何一段被删掉都会复发，所以在这里钉住（和上面 Gdk 顺序同类的静态断言）。
checks.append(('打开时按显示器工作区收尺寸（不超出屏幕）', 'get_workarea' in src))
# 用户明确要求：别限制窗口最小高度，想缩就缩。所以窗口本身不许设硬性最小尺寸。
checks.append(('窗口没有被写死最小尺寸', 'self.set_size_request(' not in src))
checks.append(('右侧上部按钮区可滚动', 'top_scroll = Gtk.ScrolledWindow()' in src))
checks.append(('日志卡有最低高度（≥120px）、且放进竖直分栏',
               'log_card.set_size_request(-1, 120)' in src and 'vpaned.pack2(log_card' in src))
checks.append(('竖直分栏真的存在', 'Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)' in src))
# 日志高度要跟着窗口高度按比例走（用户明确要求），不是写死像素
checks.append(('日志高度按窗口百分比分配', 'self._log_ratio' in src and 'configure-event' in src))
# 日志查看器：Gtk.Box.add() 不伸展 → 只显示两行；必须 pack_start(..., True, True)
checks.append(('日志查看器会填满对话框', 'area.pack_start(sw, True, True, 0)' in src
               and 'area.add(sw)' not in src))
checks.append(('对话框尺寸按窗口百分比给', 'def _dialog_size' in src and 'win_h * 0.80' in src))

# 真正构造一次窗口（用桩 GTK）：能抓到 _build() 里的解包/参数错误这类运行时问题
try:
    _win = gui.ManagerWindow()
    checks.append(('ManagerWindow() 能用桩 GTK 构造出来', True))
except Exception as exc:
    checks.append(('ManagerWindow() 能用桩 GTK 构造出来（%s: %s）'
                   % (type(exc).__name__, exc), False))

bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(('  OK  ' if ok else '  FAIL ') + n)
print('RESULT: ' + ('FAIL ' + ','.join(bad) if bad else 'PASS %d/%d' % (len(checks), len(checks))))
sys.exit(1 if bad else 0)
