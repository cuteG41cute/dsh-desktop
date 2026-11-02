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
        private readonly Func<string> _refresher;

        public TokenWindow(string title, string body, Func<string> refresher = null)
        {
            InitializeComponent();
            _refresher = refresher;
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

        /// <summary>从正文里挑出「带 token 的地址」那一行。</summary>
        private string TokenUrl()
        {
            foreach (var line in (BodyText.Text ?? "").Split('\n'))
            {
                var t = line.Trim();
                if (t.StartsWith("http", StringComparison.OrdinalIgnoreCase)
                    && t.Contains("?token=", StringComparison.OrdinalIgnoreCase))
                    return t;
            }
            return null;
        }

        private void OnCopyTokenUrl(object sender, RoutedEventArgs e)
        {
            var url = TokenUrl();
            if (string.IsNullOrEmpty(url)) { StatusText.Text = "正文里没有带 token 的地址（可能拿不到 token）"; return; }
            try
            {
                Clipboard.SetText(url);
                StatusText.Text = "带 token 的地址已复制";
            }
            catch { StatusText.Text = "复制失败（剪贴板被占用）"; }
        }

        /// <summary>重新获取：重新读一次实例的 token / cookie / 校验结果。</summary>
        private void OnRefreshToken(object sender, RoutedEventArgs e)
        {
            if (_refresher == null) { StatusText.Text = "当前窗口不支持刷新"; return; }
            try
            {
                var text = _refresher();
                if (!string.IsNullOrEmpty(text)) BodyText.Text = text;
                BodyText.ScrollToHome();
                StatusText.Text = "已重新获取（" + DateTime.Now.ToString("HH:mm:ss") + "）";
            }
            catch (Exception ex) { StatusText.Text = "重新获取失败：" + ex.Message; }
        }

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
