using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;

namespace DshManager
{
    /// <summary>
    /// 「查看 Token」窗口：和主窗口/更新窗口同一套外观（全部 DynamicResource，随主题变化）。
    /// </summary>
    public partial class TokenWindow : Window
    {
        public TokenWindow(string title, string body)
        {
            InitializeComponent();
            if (!string.IsNullOrWhiteSpace(title)) TitleText.Text = title;
            Title = title;
            BodyText.Text = body ?? "";
            Loaded += (_, _) =>
            {
                ApplyWindowRegion();
                BodyText.Focus();
                BodyText.CaretIndex = 0;
            };
            SizeChanged += (_, _) => ApplyWindowRegion();
        }

        [DllImport("user32.dll")]
        private static extern int SetWindowRgn(IntPtr hWnd, IntPtr hRgn, bool redraw);
        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateRoundRectRgn(int left, int top, int right, int bottom, int w, int h);

        private void ApplyWindowRegion()
        {
            try
            {
                var hwnd = new WindowInteropHelper(this).Handle;
                if (hwnd == IntPtr.Zero) return;
                var dpi = VisualTreeHelper.GetDpi(this).DpiScaleX;
                var w = (int)Math.Round(ActualWidth * dpi);
                var h = (int)Math.Round(ActualHeight * dpi);
                if (w <= 1 || h <= 1) return;
                var r = (int)Math.Round(26 * dpi * 2);
                var hRgn = CreateRoundRectRgn(0, 0, w + 1, h + 1, r, r);
                if (hRgn != IntPtr.Zero) SetWindowRgn(hwnd, hRgn, true);
            }
            catch { }
        }

        private void OnDrag(object sender, MouseButtonEventArgs e)
        {
            if (e.LeftButton == MouseButtonState.Pressed) DragMove();
        }

        private void OnClose(object sender, RoutedEventArgs e) => Close();

        private void OnCopyAll(object sender, RoutedEventArgs e)
        {
            try
            {
                Clipboard.SetText(BodyText.Text);
                StatusText.Text = "已复制到剪贴板";
            }
            catch { StatusText.Text = "复制失败（剪贴板被占用）"; }
        }
    }
}
