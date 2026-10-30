"""静态检查：模块级函数里用到 GLib/Gdk/Gtk/Gio/WebKit2 时，必须有局部 import。

dsh-desktop.py 的 gi 是在 run_gui() 里才 require_version + import 的，
模块级函数（比如 start_control_server）若直接引用这些名字，运行到就会 NameError
——实测踩过：NameError: name 'GLib' is not defined，窗口起不来。

用法：python3 tools/gi-scope-check.py [dsh-desktop.py]
"""
import ast
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else 'dsh-desktop/linux/dsh-desktop.py'
GI = {'GLib', 'Gdk', 'Gtk', 'Gio', 'WebKit2', 'GdkPixbuf'}

tree = ast.parse(open(PATH, encoding='utf-8').read())
bad = []
for node in tree.body:
    if not isinstance(node, ast.FunctionDef):
        continue                      # 只看模块级函数（类方法有 self 作用域，另说）
    used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in GI}
    if not used:
        continue
    imported = set()
    for n in ast.walk(node):
        if isinstance(n, ast.ImportFrom) and n.module == 'gi.repository':
            imported |= {a.name for a in n.names}
        if isinstance(n, ast.Import):
            imported |= {a.name for a in n.names if a.name in GI}
    missing = used - imported
    if missing:
        bad.append((node.name, node.lineno, sorted(missing), sorted(used)))

if bad:
    print('模块级函数缺少 gi 局部 import：')
    for name, line, miss, used in bad:
        print('  %s()  line %d  用了 %s，缺 %s' % (name, line, ','.join(used), ','.join(miss)))
    sys.exit(1)

print('OK: 所有模块级函数都自己导入了用到的 gi 名字')
