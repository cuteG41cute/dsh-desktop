"""给 MainWindow.xaml.cs 的缩放路径加诊断日志（临时，用于定位拖边不生效）。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')

PAIRS = [
    (
        "    private void BeginResize(EdgeZone zone)\n    {\n        _resizing = true;",
        "    private void BeginResize(EdgeZone zone)\n    {\n"
        "        Diag($\"begin-resize zone={zone}\");\n        _resizing = true;",
    ),
    (
        "    private void DoResize(MouseEventArgs e)\n    {\n        if (_dragZone == EdgeZone.None) return;",
        "    private void DoResize(MouseEventArgs e)\n    {\n"
        "        if (_dragZone == EdgeZone.None) return;\n"
        "        Diag($\"resize-move zone={_dragZone} size={ActualWidth:F0}x{ActualHeight:F0}\");",
    ),
    (
        "    private void EndResize()\n    {\n        if (!_resizing) return;",
        "    private void EndResize()\n    {\n        Diag($\"end-resize resizing={_resizing}\");\n"
        "        if (!_resizing) return;",
    ),
    (
        "        // 边缘 8px 内是缩放，不是拖动\n        var zone = ZoneAt(e.GetPosition(this));",
        "        // 边缘 8px 内是缩放，不是拖动\n"
        "        var pos = e.GetPosition(this);\n"
        "        var zone = ZoneAt(pos);\n"
        "        Diag($\"down at ({pos.X:F0},{pos.Y:F0}) zone={zone} \" +\n"
        "             $\"inset={Shell.Margin.Left} size={ActualWidth:F0}x{ActualHeight:F0}\");",
    ),
]


def main():
    src = io.open(P, encoding='utf-8').read()
    hits = 0
    for old, new in PAIRS:
        if old not in src:
            print('MISS:', old.splitlines()[0][:60])
            continue
        src = src.replace(old, new, 1)
        hits += 1
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('patched %d/%d' % (hits, len(PAIRS)))


if __name__ == '__main__':
    main()
