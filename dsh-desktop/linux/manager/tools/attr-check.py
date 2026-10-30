"""静态检查：gui.py 里 self.<attr> 的用法是否都有定义。

不执行 GTK，只做 AST 分析——抓的是 1.0.5 这类「启动时就抛 AttributeError 直接退出」的错误。
"""
import ast
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else 'dsh-desktop/linux/manager/dsh_manager/gui.py'
tree = ast.parse(open(PATH, encoding='utf-8').read())

# 收集：类名 -> (定义的属性集合, 使用的位置列表)
assigned = {}
used = []
for node in ast.walk(tree):
    if not isinstance(node, ast.ClassDef):
        continue
    attrs = set()
    for sub in ast.walk(node):
        # self.x = ...
        if isinstance(sub, ast.Assign):
            for t in sub.targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == 'self':
                    attrs.add(t.attr)
        # self.x: T = ...
        if isinstance(sub, ast.AnnAssign):
            t = sub.target
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == 'self':
                attrs.add(t.attr)
        # for self.x in ... / with ... as self.x
        if isinstance(sub, (ast.For, ast.AsyncFor)):
            t = sub.target
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == 'self':
                attrs.add(t.attr)
    assigned[node.name] = attrs

# 收集所有 self.<attr> 读取（Load）以及所在类
class Usage(ast.NodeVisitor):
    def __init__(self):
        self.cls = None

    def visit_ClassDef(self, node):
        prev, self.cls = self.cls, node.name
        self.generic_visit(node)
        self.cls = prev

    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Load) and isinstance(node.value, ast.Name) and node.value.id == 'self':
            used.append((self.cls, node.attr, node.lineno))
        self.generic_visit(node)


Usage().visit(tree)

# 基类方法/属性白名单（Gtk.Window 等继承来的，我们不去猜）
INHERITED = {
    'add', 'remove', 'show', 'show_all', 'hide', 'set_title', 'get_title',
    'set_default_size', 'set_position', 'set_titlebar', 'get_style_context',
    'connect', 'get_selection', 'get_buffer', 'get_line_count',
}

missing = []
for cls, attr, line in used:
    if cls is None:
        continue
    own = assigned.get(cls, set())
    # 类里没赋值，且不是从基类继承的常见方法 → 大概率是笔误
    if attr not in own and attr not in INHERITED:
        # 方法也算定义
        has_method = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                if any(isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name == attr
                       for b in node.body):
                    has_method = True
        if not has_method:
            missing.append((cls, attr, line))

if missing:
    print('可能的未定义属性（%d 处）:' % len(missing))
    for cls, attr, line in missing:
        print('  %s.%s  (line %d)' % (cls, attr, line))
    sys.exit(1)

print('OK: 所有 self.<attr> 都在类内定义或来自基类')
for cls, attrs in sorted(assigned.items()):
    print('  %-14s 定义 %2d 个属性' % (cls, len(attrs)))
