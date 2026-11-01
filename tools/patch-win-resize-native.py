"""把缩放改成纯 Win32 手动循环（WM_NCHITTEST 定区域 + 按下/移动/抬起自己 SetWindowPos）。

上一版只返回 HTLEFT/HTRIGHT 让系统跑循环，实测窗口不动（没有 WS_THICKFRAME 时
DefWindowProc 不进入 SC_SIZE）。这一版不依赖任何窗口样式：自己抓鼠标、自己算新矩形。
"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')

OLD_START = "    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)"
OLD_END = "        handled = true;\n        return new IntPtr(hit);\n    }"

NEW = '''    private IntPtr _winHwnd;
    private int _hitZone;
    private bool _nativeResize;
    private Rect _nativeStartRect;
    private POINT _nativeStartMouse;

    [DllImport("user32.dll")]
    private static extern IntPtr SetCapture(IntPtr h);
    [DllImport("user32.dll")]
    private static extern bool ReleaseCapture();
    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);

    private const int WM_LBUTTONDOWN = 0x0201, WM_NCLBUTTONDOWN = 0x00A1,
        WM_MOUSEMOVE = 0x0200, WM_LBUTTONUP = 0x0202, WM_CAPTURECHANGED = 0x0215;
    private const uint SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010;

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        _winHwnd = hwnd;

        if (msg == WM_NCHITTEST)
        {
            _hitZone = HitZoneAtCursor();
            if (_hitZone == 0) return IntPtr.Zero;
            handled = true;
            return new IntPtr(_hitZone);
        }

        // 在边缘按下：接管鼠标，自己做缩放循环（不依赖 WS_THICKFRAME）
        if ((msg == WM_NCLBUTTONDOWN || msg == WM_LBUTTONDOWN) && !_isMaximized)
        {
            var zone = _hitZone != 0 ? _hitZone : HitZoneAtCursor();
            if (zone != 0 && zone != HTCLIENT)
            {
                _hitZone = zone;
                POINT pt;
                GetCursorPos(out pt);
                _nativeStartMouse = pt;
                _nativeStartRect = new Rect(Left, Top, ActualWidth, ActualHeight);
                _nativeResize = true;
                SetCapture(hwnd);
                Diag($"resize-start zone={zone} at ({pt.X},{pt.Y})");
                handled = true;
                return IntPtr.Zero;
            }
        }

        if (msg == WM_MOUSEMOVE && _nativeResize)
        {
            DoNativeResize();
            handled = true;
            return IntPtr.Zero;
        }

        if ((msg == WM_LBUTTONUP || msg == WM_CAPTURECHANGED) && _nativeResize)
        {
            _nativeResize = false;
            ReleaseCapture();
            _hitZone = 0;
            Diag("resize-end");
            handled = true;
            return IntPtr.Zero;
        }

        return IntPtr.Zero;
    }

    /// <summary>把当前光标位置映射成 Win32 命中码（0 = 不在缩放带上）。</summary>
    private int HitZoneAtCursor()
    {
        POINT pt;
        if (!GetCursorPos(out pt)) return 0;
        var scale = Dpi;
        var origin = PointToScreen(new Point(0, 0));
        var x = pt.X - origin.X;
        var y = pt.Y - origin.Y;
        var w = ActualWidth * scale;
        var h = ActualHeight * scale;
        var inset = Shell.Margin.Left * scale;
        var grip = GripSize * scale;

        var inside = x >= inset && x <= w - inset && y >= inset && y <= h - inset;
        if (!inside) return 0;

        var inLeft = x <= inset + grip;
        var inRight = x >= w - inset - grip;
        var inTop = y <= inset + grip;
        var inBottom = y >= h - inset - grip;

        if (inLeft && inTop) return HTTOPLEFT;
        if (inRight && inTop) return HTTOPRIGHT;
        if (inLeft && inBottom) return HTBOTTOMLEFT;
        if (inRight && inBottom) return HTBOTTOMRIGHT;
        if (inLeft) return HTLEFT;
        if (inRight) return HTRIGHT;
        if (inTop) return HTTOP;
        if (inBottom) return HTBOTTOM;
        return 0;
    }

    private void DoNativeResize()
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
    }
'''


def main():
    src = io.open(P, encoding='utf-8').read()
    start = src.index(OLD_START)
    end = src.index(OLD_END, start) + len(OLD_END)
    src = src[:start] + NEW + src[end:]
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('replaced WndProc:', start, '->', end)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
