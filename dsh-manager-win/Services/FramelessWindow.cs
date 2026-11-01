using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;

namespace DshManager.Services;

/// <summary>
/// 无边框窗口的两件系统活：
///   1. 圆角 —— 管理器和会话窗口画法不一样（见 SetCornerPreference 注释）；
///   2. 缩放 —— 会话窗口里装着 WebView2（原生子窗口），不能在 WPF 里做命中测试，
///      也不能靠 WindowChrome 的 ResizeBorderThickness（实测拿不到缩放循环），
///      所以和 MainWindow 一样：WM_NCHITTEST 给命中码 + 自己跑 SetWindowPos 循环。
/// </summary>
internal static class FramelessWindow
{
    private const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;

    public const int Default = 0;    // DWMWCP_DEFAULT（由系统决定）
    public const int DoNotRound = 1; // DWMWCP_DONOTROUND
    public const int Round = 2;      // DWMWCP_ROUND
    public const int RoundSmall = 3; // DWMWCP_ROUNDSMALL

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    /// <summary>在窗口句柄就绪后设置圆角偏好（失败就算了，不影响功能）。</summary>
    public static void SetCornerPreference(Window win, int preference)
    {
        void Apply()
        {
            try
            {
                var hwnd = new WindowInteropHelper(win).Handle;
                if (hwnd == IntPtr.Zero) return;
                var value = preference;
                DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ref value, sizeof(int));
            }
            catch { }
        }

        win.SourceInitialized += (_, _) => Apply();
        // WPF 应用 WindowChrome 时会再改一次这个属性，窗口显示出来之后要覆盖回去
        win.Loaded += (_, _) =>
        {
            Apply();
            var timer = new System.Windows.Threading.DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(300),
            };
            timer.Tick += (_, _) => { timer.Stop(); Apply(); };
            timer.Start();
        };
    }

    // ---------------------------------------------------------------- 缩放
    private const int WM_NCHITTEST = 0x0084, WM_SETCURSOR = 0x0020;
    private const int HTCLIENT = 1, HTLEFT = 10, HTRIGHT = 11, HTTOP = 12, HTTOPLEFT = 13,
        HTTOPRIGHT = 14, HTBOTTOM = 15, HTBOTTOMLEFT = 16, HTBOTTOMRIGHT = 17;
    private const int WM_LBUTTONDOWN = 0x0201, WM_NCLBUTTONDOWN = 0x00A1,
        WM_MOUSEMOVE = 0x0200, WM_LBUTTONUP = 0x0202, WM_CAPTURECHANGED = 0x0215;
    private const uint SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010;

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT { public int X, Y; }

    [StructLayout(LayoutKind.Sequential)]
    private struct RECTW { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")] private static extern bool GetCursorPos(out POINT p);
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr h, out RECTW r);
    [DllImport("user32.dll")] private static extern IntPtr SetCapture(IntPtr h);
    [DllImport("user32.dll")] private static extern bool ReleaseCapture();
    [DllImport("user32.dll")] private static extern bool SetWindowPos(
        IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] private static extern IntPtr SetCursor(IntPtr cursor);
    [DllImport("user32.dll")] private static extern IntPtr LoadCursor(IntPtr instance, IntPtr name);

    private static readonly IntPtr CursorWE = LoadCursor(IntPtr.Zero, new IntPtr(32644));   // IDC_SIZEWE
    private static readonly IntPtr CursorNS = LoadCursor(IntPtr.Zero, new IntPtr(32645));   // IDC_SIZENS
    private static readonly IntPtr CursorNWSE = LoadCursor(IntPtr.Zero, new IntPtr(32642)); // IDC_SIZENWSE
    private static readonly IntPtr CursorNESW = LoadCursor(IntPtr.Zero, new IntPtr(32643)); // IDC_SIZENESW

    private sealed class ResizeState
    {
        public IntPtr Hwnd;
        public int Zone;
        public bool Resizing;
        public POINT StartMouse;
        public RECTW StartRect;
    }

    /// <summary>接管窗口四边的缩放（grip = 从窗口边往里多少 DIP 算边缘）。</summary>
    public static void EnableResize(Window win, double grip, Func<bool> isMaximized)
    {
        var state = new ResizeState();
        var dpi = 1.0;
        try { dpi = VisualTreeHelper.GetDpi(win).DpiScaleX; } catch { }

        IntPtr Hook(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
        {
            state.Hwnd = hwnd;

            if (msg == WM_NCHITTEST)
            {
                state.Zone = HitZone(win, grip, isMaximized());
                if (state.Zone == 0) return IntPtr.Zero;
                handled = true;
                return new IntPtr(state.Zone);
            }

            if (msg == WM_SETCURSOR && state.Zone != 0 && !state.Resizing)
            {
                var cursor = CursorFor(state.Zone);
                if (cursor != IntPtr.Zero)
                {
                    SetCursor(cursor);
                    handled = true;
                    return new IntPtr(1);
                }
            }

            if ((msg == WM_NCLBUTTONDOWN || msg == WM_LBUTTONDOWN) && !isMaximized())
            {
                var zone = state.Zone != 0 ? state.Zone : HitZone(win, grip, false);
                if (zone != 0 && zone != HTCLIENT)
                {
                    state.Zone = zone;
                    GetCursorPos(out var pt);
                    state.StartMouse = pt;
                    GetWindowRect(hwnd, out state.StartRect);
                    state.Resizing = true;
                    SetCapture(hwnd);
                    handled = true;
                    return IntPtr.Zero;
                }
            }

            if (msg == WM_MOUSEMOVE && state.Resizing)
            {
                DoResize(win, state, dpi);
                handled = true;
                return IntPtr.Zero;
            }

            if ((msg == WM_LBUTTONUP || msg == WM_CAPTURECHANGED) && state.Resizing)
            {
                state.Resizing = false;
                ReleaseCapture();
                state.Zone = 0;
                handled = true;
                return IntPtr.Zero;
            }

            return IntPtr.Zero;
        }

        win.SourceInitialized += (_, _) =>
        {
            if (PresentationSource.FromVisual(win) is HwndSource src) src.AddHook(Hook);
        };
    }

    private static IntPtr CursorFor(int zone) => zone switch
    {
        HTLEFT or HTRIGHT => CursorWE,
        HTTOP or HTBOTTOM => CursorNS,
        HTTOPLEFT or HTBOTTOMRIGHT => CursorNWSE,
        HTTOPRIGHT or HTBOTTOMLEFT => CursorNESW,
        _ => IntPtr.Zero,
    };

    /// <summary>把光标位置映射成 Win32 命中码（0 = 不在缩放带上）。</summary>
    private static int HitZone(Window win, double grip, bool isMaximized)
    {
        if (isMaximized) return 0;
        if (!GetCursorPos(out var pt)) return 0;
        var scale = 1.0;
        try { scale = VisualTreeHelper.GetDpi(win).DpiScaleX; } catch { }
        var origin = win.PointToScreen(new Point(0, 0));
        var x = pt.X - origin.X;
        var y = pt.Y - origin.Y;
        var w = win.ActualWidth * scale;
        var h = win.ActualHeight * scale;
        var gripPx = grip * scale;

        if (x < 0 || x > w || y < 0 || y > h) return 0;

        var inLeft = x <= gripPx;
        var inRight = x >= w - gripPx;
        var inTop = y <= gripPx;
        var inBottom = y >= h - gripPx;

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

    private static void DoResize(Window win, ResizeState st, double dpi)
    {
        if (st.Hwnd == IntPtr.Zero) return;
        if (!GetCursorPos(out var pt)) return;

        // 全程物理像素：起点是按下时的屏幕矩形，位移是光标的屏幕差分。
        // 右/下边只改宽高（位置不动），左/上边才移动窗口，两者不会互相干扰。
        var dx = pt.X - st.StartMouse.X;
        var dy = pt.Y - st.StartMouse.Y;
        var minW = (int)Math.Round(win.MinWidth * dpi);
        var minH = (int)Math.Round(win.MinHeight * dpi);
        if (minW < 320) minW = 320;
        if (minH < 240) minH = 240;

        var left = st.StartRect.Left;
        var top = st.StartRect.Top;
        var right = st.StartRect.Right;
        var bottom = st.StartRect.Bottom;

        if (st.Zone is HTLEFT or HTTOPLEFT or HTBOTTOMLEFT)
            left = Math.Min(st.StartRect.Left + dx, right - minW);
        if (st.Zone is HTRIGHT or HTTOPRIGHT or HTBOTTOMRIGHT)
            right = Math.Max(st.StartRect.Right + dx, left + minW);
        if (st.Zone is HTTOP or HTTOPLEFT or HTTOPRIGHT)
            top = Math.Min(st.StartRect.Top + dy, bottom - minH);
        if (st.Zone is HTBOTTOM or HTBOTTOMLEFT or HTBOTTOMRIGHT)
            bottom = Math.Max(st.StartRect.Bottom + dy, top + minH);

        var w = Math.Max(minW, right - left);
        var h = Math.Max(minH, bottom - top);
        SetWindowPos(st.Hwnd, IntPtr.Zero, left, top, w, h, SWP_NOZORDER | SWP_NOACTIVATE);
    }
}
