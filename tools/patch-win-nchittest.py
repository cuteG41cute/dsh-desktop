"""改用 Win32 的 WM_NCHITTEST 做窗口缩放（WPF 鼠标事件在分层窗口上不可靠）。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')

HOOK = '''
    // ---------------------------------------------------------------- Win32 命中测试缩放
    // 分层窗口（AllowsTransparency）里 WPF 的鼠标事件/捕获经常拿不到，自己算 Left/Width
    // 又会出现「窗口不随动、松手不结束」。改成返回 HTLEFT/HTRIGHT… 让 Windows 自己跑
    // 缩放循环：随动、松手结束、边界光标都是系统行为，比手写稳。
    private const int WM_NCHITTEST = 0x0084;
    private const int WM_SETCURSOR = 0x0020;
    private const int HTCLIENT = 1, HTLEFT = 10, HTRIGHT = 11, HTTOP = 12, HTTOPLEFT = 13,
        HTTOPRIGHT = 14, HTBOTTOM = 15, HTBOTTOMLEFT = 16, HTBOTTOMRIGHT = 17;

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        var src = PresentationSource.FromVisual(this) as HwndSource;
        src?.AddHook(WndProc);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT { public int X, Y; }

    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out POINT p);

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg != WM_NCHITTEST) return IntPtr.Zero;

        POINT pt;
        if (!GetCursorPos(out pt)) return IntPtr.Zero;
        var scale = Dpi;
        // 窗口左上角（屏幕物理像素）
        var origin = PointToScreen(new Point(0, 0));
        var x = pt.X - origin.X;
        var y = pt.Y - origin.Y;
        var w = ActualWidth * scale;
        var h = ActualHeight * scale;
        var inset = Shell.Margin.Left * scale;          // 透明外沿（14 DIP）
        var grip = GripSize * scale;                    // 抓取带宽（8 DIP）

        var inLeft = x >= inset && x <= inset + grip;
        var inRight = x <= w - inset && x >= w - inset - grip;
        var inTop = y >= inset && y <= inset + grip;
        var inBottom = y <= h - inset && y >= h - inset - grip;
        var inside = x >= inset && x <= w - inset && y >= inset && y <= h - inset;

        int hit = 0;
        if (inside && !_isMaximized)
        {
            if (inLeft && inTop) hit = HTTOPLEFT;
            else if (inRight && inTop) hit = HTTOPRIGHT;
            else if (inLeft && inBottom) hit = HTBOTTOMLEFT;
            else if (inRight && inBottom) hit = HTBOTTOMRIGHT;
            else if (inLeft) hit = HTLEFT;
            else if (inRight) hit = HTRIGHT;
            else if (inTop) hit = HTTOP;
            else if (inBottom) hit = HTBOTTOM;
        }
        if (hit == 0) return IntPtr.Zero;

        Diag($"nchittest ({x},{y}) -> {hit}");
        handled = true;
        return new IntPtr(hit);
    }
'''

PAIRS = [
    # 1) 拖动不再自己算缩放：边缘交给系统
    (
        """        // 边缘 8px 内是缩放，不是拖动
        var pos = e.GetPosition(this);
        var zone = ZoneAt(pos);
        Diag($"down at ({pos.X:F0},{pos.Y:F0}) zone={zone} " +
             $"inset={Shell.Margin.Left} size={ActualWidth:F0}x{ActualHeight:F0}");
        if (zone != EdgeZone.None)
        {
            e.Handled = true;
            BeginResize(zone);
            return;
        }""",
        """        // 边缘交给 Win32 的 WM_NCHITTEST 缩放（见 WndProc），这里只管拖动
        var pos = e.GetPosition(this);
        Diag($"down at ({pos.X:F0},{pos.Y:F0}) size={ActualWidth:F0}x{ActualHeight:F0}");""",
    ),
    # 2) 插入 Win32 钩子
    (
        "    // ---------------------------------------------------------------- 缩放 / 拖动 / 圆角",
        HOOK + "\n    // ---------------------------------------------------------------- 缩放 / 拖动 / 圆角",
    ),
]


def main():
    src = io.open(P, encoding='utf-8').read()
    for old, new in PAIRS:
        if old not in src:
            print('MISS:', old.splitlines()[0][:70])
            return 1
        src = src.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('patched ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
