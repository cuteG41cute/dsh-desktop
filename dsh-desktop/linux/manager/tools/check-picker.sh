#!/usr/bin/env bash
# ============================================================================
# 验证「版本选择器」在你这台机器的 GTK 上到底能不能用（不需要打开管理器）。
#
# 做的事：用系统 python3 + 已安装的 dsh_manager，在临时窗口里真建一个 VersionPicker，
# 然后检查三件事：
#   1. 预设版本号是否真的进了下拉框（数量 > 1）；
#   2. 选中第 2 项后 get_value() 是否跟着变；
#   3. 手动输入框是否优先（输入 9.9.9 后 get_value() 应该是 9.9.9）。
#
# 用法：bash check-picker.sh
# ============================================================================
set -u

LIB="${LIB:-/usr/lib/dsh-manager}"
if [ ! -d "$LIB/dsh_manager" ]; then
    echo "找不到 $LIB/dsh_manager —— 先装 dsh-manager 这个 deb（或设 LIB=/path）"
    exit 1
fi

PYTHONPATH="$LIB" python3 - <<'PY'
import sys
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

ok, _argv = Gtk.init_check(sys.argv[:1])
if not ok:
    print('没有可用的图形显示（DISPLAY/WAYLAND_DISPLAY 都没起来？）')
    sys.exit(1)

from dsh_manager.gui import VersionPicker

win = Gtk.Window()
win.set_default_size(700, 120)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
win.add(box)

picker = VersionPicker(['latest', '0.2.1-rc.5', '0.2.0-rc.2'], value='latest',
                       fetcher=lambda: ['latest', '0.2.1-rc.5'])
box.pack_start(picker, False, False, 0)
win.show_all()

checks = []


def count_items():
    model = picker._combo.get_model()
    return 0 if model is None else model.iter_n_children(None)


checks.append(('预设版本进了下拉框（%d 项）' % count_items(), count_items() >= 3))
checks.append(('初始值 latest', picker.get_value() == 'latest'))

picker._combo.set_active(1)
GLib.main_context_default().iteration(False)
checks.append(('选中第 2 项后 get_value() 跟着变（%r）' % picker.get_value(),
               picker.get_value() == '0.2.1-rc.5'))

picker._entry.set_text('9.9.9')
checks.append(('手动输入优先（%r）' % picker.get_value(), picker.get_value() == '9.9.9'))
picker._entry.set_text('')

# 覆盖旧列表：新列表进来后数量应变
picker.set_options(['latest', '1.1.1', '2.2.2'])
checks.append(('set_options 覆盖旧列表（%d 项）' % count_items(), count_items() == 3))

# 「更新」按钮：真跑一次 fetcher（假数据源，不联网）
if picker._btn is not None:
    picker._on_refresh()
    for _ in range(40):
        GLib.main_context_default().iteration(False)
        if picker._btn.get_sensitive():
            break
        import time
        time.sleep(0.05)
    checks.append(('「更新」按钮刷新后仍然是 3 项（latest + 2）', count_items() == 3))
else:
    checks.append(('「更新」按钮存在', False))

failed = [n for n, okk in checks if not okk]
for n, okk in checks:
    print(('  OK   ' if okk else '  FAIL ') + n)
print('RESULT: %s %d/%d' % ('PASS' if not failed else 'FAIL',
                            len(checks) - len(failed), len(checks)))
win.destroy()
sys.exit(0 if not failed else 1)
PY
