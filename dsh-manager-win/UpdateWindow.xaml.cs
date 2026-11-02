using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;

namespace DshManager
{
    /// <summary>
    /// 更新 dsh / Node：两个抽屉式下拉，风格与主题跟随主窗口（全部 DynamicResource）。
    /// </summary>
    public partial class UpdateWindow : Window
    {
        private readonly Services.DshInstance _inst;
        private readonly List<string> _dshVersions;
        private readonly List<string> _nodeVersions;
        private readonly string _currentNode;

        public string SelectedDsh { get; private set; }
        public string SelectedNode { get; private set; }

        public UpdateWindow(Services.DshInstance inst, IEnumerable<string> dshVersions,
                            IEnumerable<string> nodeVersions)
        {
            InitializeComponent();
            _inst = inst;
            var cur = inst.DshVersion ?? "";
            _currentNode = inst.NodeVersion ?? "";
            _dshVersions = dshVersions?.Where(v => !string.IsNullOrWhiteSpace(v)).Distinct().ToList()
                           ?? new List<string>();
            _nodeVersions = nodeVersions?.Where(v => !string.IsNullOrWhiteSpace(v)).Distinct().ToList()
                            ?? new List<string>();

            SubtitleText.Text = "实例 " + inst.Label + " · 当前 dsh " + (string.IsNullOrWhiteSpace(cur) ? "未知" : cur)
                                + " · Node " + (string.IsNullOrWhiteSpace(_currentNode) ? "未知" : _currentNode)
                                + " · 来源 " + inst.Source;

            // 下拉里第一项永远显示「不动」；其余是候选版本（新→旧）
            var dshItems = new List<string> { "保持当前（" + (string.IsNullOrWhiteSpace(cur) ? "未知" : cur) + "）" };
            dshItems.AddRange(_dshVersions);
            DshBox.ItemsSource = dshItems;
            DshBox.SelectedIndex = 0;
            DshHint.Text = "当前版本：" + (string.IsNullOrWhiteSpace(cur) ? "未知" : cur)
                           + "；想升级或降级就选一个版本，默认「保持当前」。";

            var nodeItems = new List<string> { "保持当前（" + (string.IsNullOrWhiteSpace(_currentNode) ? "未知" : _currentNode) + "）" };
            nodeItems.AddRange(_nodeVersions);
            NodeBox.ItemsSource = nodeItems;
            NodeBox.SelectedIndex = 0;

            Loaded += (_, _) =>
            {
                bool hasPortable = System.IO.File.Exists(
                    System.IO.Path.Combine(inst.Dir ?? "", "node", "node.exe"));
                NodeBox.IsEnabled = hasPortable && _nodeVersions.Count > 0;
                NodeHint.Text = hasPortable
                    ? "实例自带便携 Node；选中某版本会把 <实例目录>\\node 换成该版本。"
                    : "这个实例用的是系统 Node（或没有便携 Node），管理器不改它。";
                try
                {
                    if (!Services.InstanceActions.IsManaged(inst))
                    {
                        HintText.Text = "系统安装（" + inst.Source + "）：管理器不会改动它，只列出可用版本。";
                        ApplyBtn.IsEnabled = false;
                    }
                    else HintText.Text = "选好版本后点「应用」；升级与降级都支持，改完需要重启服务才生效。";
                }
                catch { }
                ApplyWindowRegion();
            };
            SizeChanged += (_, _) => ApplyWindowRegion();
        }

        [DllImport("user32.dll")]
        private static extern int SetWindowRgn(IntPtr hWnd, IntPtr hRgn, bool redraw);
        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateRoundRectRgn(int left, int top, int right, int bottom, int w, int h);

        /// <summary>窗口圆角：和主窗口一样用 Region 裁，避免外面露出灰色直角。</summary>
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

        private void OnApply(object sender, RoutedEventArgs e)
        {
            if (DshBox.SelectedIndex > 0) SelectedDsh = DshBox.SelectedItem as string;
            if (NodeBox.SelectedIndex > 0) SelectedNode = NodeBox.SelectedItem as string;
            DialogResult = true;
            Close();
        }
    }
}
