"""把窗口缩放改成「全程物理像素」：起点用 GetWindowRect，位移用 GetCursorPos 差分。

上一版混用了 DIP（WPF 的 Left/Top/Width/Height）和物理像素（SetWindowPos），
上边缘往下拖时窗口会塌掉。现在只用屏幕物理矩形 + 光标差分，DIP 只在算最小尺寸时用一次。
"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')

OLD_DO = '''    private void DoNativeResize()
    {
        POINT pt;
        if (!GetCursorPos(out pt)) return;
        var scale = Dpi;
        var dx = (pt.X - _nativeStartMouse.X) / scale;
        var dy = (pt.Y - _nativeStartMouse.Y) / scale;
        var r = _nativeStartRect;

        var left = r.Left;
        var top = r.Top;
        var width = r.Width;
        var height = r.Height;

        switch (_hitZone)
        {
            case HTLEFT:
            case HTTOPLEFT:
            case HTBOTTOMLEFT:
                left = Math.Min(r.Left + dx, r.Right - MinWidth);
                width = r.Right - left;
                break;
        }
        switch (_hitZone)
        {
            case HTRIGHT:
            case HTTOPRIGHT:
            case HTBOTTOMRIGHT:
                width = Math.Max(MinWidth, r.Width + dx);
                break;
        }
        switch (_hitZone)
        {
            case HTTOP:
            case HTTOPLEFT:
            case HTTOPRIGHT:
                top = Math.Min(r.Top + dy, r.Bottom - MinHeight);
                height = r.Bottom - top;
                break;
        }
        switch (_hitZone)
        {
            case HTBOTTOM:
            case HTBOTTOMLEFT:
            case HTBOTTOMRIGHT:
                height = Math.Max(MinHeight, r.Height + dy);
                break;
        }

        if (_winHwnd == IntPtr.Zero) return;
        var sp = PointToScreen(new Point(0, 0));
        var px = (int)Math.Round(sp.X + (left - r.Left) * scale);
        var py = (int)Math.Round(sp.Y + (top - r.Top) * scale);
        var pw = (int)Math.Round(width * scale);
        var ph = (int)Math.Round(height * scale);
        SetWindowPos(_winHwnd, IntPtr.Zero, px, py, pw, ph, SWP_NOZORDER | SWP_NOACTIVATE);
    }'''

NEW_DO = '''    private void DoNativeResize()
    {
        POINT pt;
        if (!GetCursorPos(out pt)) return;
        if (_winHwnd == IntPtr.Zero) return;

        // 全程物理像素：起点是按下时的屏幕矩形，位移是光标的屏幕差分。
        // 这样右/下边只会改宽高（窗口位置不动），左/上边才会移动窗口，不会互相干扰。
        var dx = pt.X - _nativeStartMouse.X;
        var dy = pt.Y - _nativeStartMouse.Y;
        var minW = (int)Math.Round(MinWidth * Dpi);
        var minH = (int)Math.Round(MinHeight * Dpi);

        var left = _nativeStartPhys.Left;
        var top = _nativeStartPhys.Top;
        var right = _nativeStartPhys.Right;
        var bottom = _nativeStartPhys.Bottom;

        switch (_hitZone)
        {
            case HTLEFT:
            case HTTOPLEFT:
            case HTBOTTOMLEFT:
                left = Math.Min(_nativeStartPhys.Left + dx, right - minW);
                break;
        }
        switch (_hitZone)
        {
            case HTRIGHT:
            case HTTOPRIGHT:
            case HTBOTTOMRIGHT:
                right = Math.Max(_nativeStartPhys.Right + dx, left + minW);
                break;
        }
        switch (_hitZone)
        {
            case HTTOP:
            case HTTOPLEFT:
            case HTTOPRIGHT:
                top = Math.Min(_nativeStartPhys.Top + dy, bottom - minH);
                break;
        }
        switch (_hitZone)
        {
            case HTBOTTOM:
            case HTBOTTOMLEFT:
            case HTBOTTOMRIGHT:
                bottom = Math.Max(_nativeStartPhys.Bottom + dy, top + minH);
                break;
        }

        var x = left;
        var y = top;
        var w = Math.Max(minW, right - left);
        var h = Math.Max(minH, bottom - top);
        Diag($"resize move zone={_hitZone} d=({dx},{dy}) -> ({x},{y}) {w}x{h}");
        SetWindowPos(_winHwnd, IntPtr.Zero, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE);
    }'''

OLD_START = '''                _hitZone = zone;
                POINT pt;
                GetCursorPos(out pt);
                _nativeStartMouse = pt;
                _nativeStartRect = new Rect(Left, Top, ActualWidth, ActualHeight);'''

NEW_START = '''                _hitZone = zone;
                POINT pt;
                GetCursorPos(out pt);
                _nativeStartMouse = pt;
                GetWindowRect(hwnd, out _nativeStartPhys);
                Diag($"resize-start zone={zone} rect=({_nativeStartPhys.Left},{_nativeStartPhys.Top})" +
                     $"-({_nativeStartPhys.Right},{_nativeStartPhys.Bottom})");'''

FIELDS_OLD = '''    private bool _nativeResize;
    private Rect _nativeStartRect;
    private POINT _nativeStartMouse;'''

FIELDS_NEW = '''    private bool _nativeResize;
    private POINT _nativeStartMouse;

    [StructLayout(LayoutKind.Sequential)]
    private struct RECTW { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr h, out RECTW r);

    private RECTW _nativeStartPhys;'''


def main():
    src = io.open(P, encoding='utf-8').read()
    for old, new in ((FIELDS_OLD, FIELDS_NEW), (OLD_DO, NEW_DO), (OLD_START, NEW_START)):
        if old not in src:
            print('MISS:', old.splitlines()[0][:70])
            return 1
        src = src.replace(old, new, 1)
    # 去掉重复的 resize-start 日志（新的一段已经带了更详细的）
    src = src.replace('                Diag($"resize-start zone={zone} at ({pt.X},{pt.Y})");\n', '')
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('patched physical resize')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
