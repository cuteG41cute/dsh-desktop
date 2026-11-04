using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;

namespace DshManager
{
    /// <summary>「窗口功能」：列出内置会话窗口的增强能力，并给可开关项加开关（立即保存 + 重载窗口）。</summary>
    public partial class FeaturesWindow : Window
    {
        private bool _loading;

        public FeaturesWindow()
        {
            InitializeComponent();
            _loading = true;
            PanCheck.IsChecked = Services.AppSettings.WebPan;
            DragOutCheck.IsChecked = Services.AppSettings.WebDragOut;
            _loading = false;
            Loaded += (_, _) => ApplyWindowRegion();
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

        private void OnTogglePan(object sender, MouseButtonEventArgs e) { PanCheck.IsChecked = !(PanCheck.IsChecked == true); Apply(); }
        private void OnToggleDragOut(object sender, MouseButtonEventArgs e) { DragOutCheck.IsChecked = !(DragOutCheck.IsChecked == true); Apply(); }
        private void OnPanToggled(object sender, RoutedEventArgs e) => Apply();
        private void OnDragOutToggled(object sender, RoutedEventArgs e) => Apply();

        private void Apply()
        {
            if (_loading) return;
            Services.AppSettings.WebPan = PanCheck.IsChecked == true;
            Services.AppSettings.WebDragOut = DragOutCheck.IsChecked == true;
            Services.AppSettings.Save();
            DshWebWindow.ReloadAll();
            StatusText.Text = "已保存，并重载了已打开的会话窗口（"
                              + (PanCheck.IsChecked == true ? "平移 开" : "平移 关") + " · "
                              + (DragOutCheck.IsChecked == true ? "拖出 开" : "拖出 关") + "）";
        }
    }
}
