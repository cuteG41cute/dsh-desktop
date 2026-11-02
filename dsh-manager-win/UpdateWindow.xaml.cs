using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace DshManager
{
    /// <summary>
    /// 更新 dsh / Node：窗口先弹出，版本列表在窗口里异步拉取（顶部转圈），
    /// 底部「检查更新」可随时重拉。风格随主窗口主题。
    /// </summary>
    public partial class UpdateWindow : Window
    {
        private readonly Services.DshInstance _inst;
        private readonly string _currentDsh;
        private readonly string _currentNode;
        private List<string> _dshVersions = new();
        private List<string> _nodeVersions = new();
        private bool _loading;

        public string SelectedDsh { get; private set; }
        public string SelectedNode { get; private set; }

        public UpdateWindow(Services.DshInstance inst)
        {
            InitializeComponent();
            _inst = inst;
            _currentDsh = inst.DshVersion ?? "";
            _currentNode = inst.NodeVersion ?? "";
            SubtitleText.Text = "实例 " + inst.Label
                                + " · 当前 dsh " + (string.IsNullOrWhiteSpace(_currentDsh) ? "未知" : _currentDsh)
                                + " · Node " + (string.IsNullOrWhiteSpace(_currentNode) ? "未知" : _currentNode)
                                + " · 来源 " + inst.Source;

            Loaded += async (_, _) =>
            {
                try
                {
                    bool hasPortable = System.IO.File.Exists(
                        System.IO.Path.Combine(inst.Dir ?? "", "node", "node.exe"));
                    NodeBox.IsEnabled = false;
                    NodeHint.Text = hasPortable
                        ? "实例自带便携 Node；选中某版本会把 <实例目录>\\node 换成该版本。"
                        : "这个实例用的是系统 Node（或没有便携 Node），管理器不改它。";
                    if (!Services.InstanceActions.IsManaged(inst))
                    {
                        HintText.Text = "系统安装（" + inst.Source + "）：管理器不会改动它，只列出可用版本。";
                        ApplyBtn.IsEnabled = false;
                    }
                    else HintText.Text = "选好版本后点「应用」；升级与降级都支持，改完需要重启服务才生效。";
                }
                catch { }
                ApplyWindowRegion();
                await LoadVersionsAsync();
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

        /// <summary>
        /// 转圈：用 DispatcherTimer 每 30ms 给 RotateTransform.Angle 加一点。
        /// （试过 XAML EventTrigger + Storyboard、也试过代码 Storyboard.Begin()，
        ///   在这台机器上 GetCurrentState 一直是 Stopped、界面不动 —— 定时器最可靠。）
        /// </summary>
        private DispatcherTimer _spinTimer;
        private double _spinAngle;

        private void StartSpin()
        {
            try
            {
                if (_spinTimer == null)
                {
                    _spinTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(30) };
                    _spinTimer.Tick += (_, _) =>
                    {
                        _spinAngle = (_spinAngle + 12) % 360;
                        if (SpinnerRotate != null) SpinnerRotate.Angle = _spinAngle;
                    };
                }
                if (!_spinTimer.IsEnabled) _spinTimer.Start();
                LogSpin("timer start");
            }
            catch (Exception ex) { LogSpin("start failed: " + ex.Message); }
        }

        private void StopSpin()
        {
            try
            {
                if (_spinTimer != null && _spinTimer.IsEnabled) _spinTimer.Stop();
                LogSpin("timer stop angle=" + Math.Round(_spinAngle));
            }
            catch { }
        }

        private static void LogSpin(string msg)
        {
            try
            {
                var dir = System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "dsh-manager");
                System.IO.Directory.CreateDirectory(dir);
                System.IO.File.AppendAllText(System.IO.Path.Combine(dir, "ui.log"),
                    DateTime.Now.ToString("HH:mm:ss.fff ") + "spin " + msg + Environment.NewLine);
            }
            catch { }
        }

        private void SetLoading(bool on, string text = null)
        {
            _loading = on;
            Spinner.Visibility = on ? Visibility.Visible : Visibility.Collapsed;
            LoadingText.Text = on ? (text ?? "正在获取版本列表…") : "";
            LoadingText.Visibility = on ? Visibility.Visible : Visibility.Collapsed;
            RefreshBtn.IsEnabled = !on;
            if (!on) StopSpin();
            if (on)
            {
                StartSpin();
                DshBox.IsEnabled = false;
                NodeBox.IsEnabled = false;
                ApplyBtn.IsEnabled = false;
            }
        }

        private async System.Threading.Tasks.Task LoadVersionsAsync()
        {
            if (_loading) return;
            SetLoading(true);
            try
            {
                var dsh = await Services.VersionCatalog.DshVersionsAsync();
                _dshVersions = dsh.Where(v => !string.IsNullOrWhiteSpace(v) && v != "latest")
                                  .Reverse().ToList();
                var node = await Services.VersionCatalog.NodeVersionsAsync();
                _nodeVersions = node.Where(v => !string.IsNullOrWhiteSpace(v)
                                                && v != Services.VersionCatalog.SystemNode && v != "latest")
                                    .ToList();
                FillCombos();
                LoadingText.Text = "";
                SetLoading(false);
                DshHint.Text = "当前版本：" + (string.IsNullOrWhiteSpace(_currentDsh) ? "未知" : _currentDsh)
                               + "（共 " + _dshVersions.Count + " 个可选版本）";
                var portable = System.IO.File.Exists(
                    System.IO.Path.Combine(_inst.Dir ?? "", "node", "node.exe"));
                NodeHint.Text = portable
                    ? "当前 Node：" + (string.IsNullOrWhiteSpace(_currentNode) ? "未知" : _currentNode)
                      + "（共 " + _nodeVersions.Count + " 个可选版本）"
                    : "这个实例用的是系统 Node，管理器不改它。";
                DshBox.IsEnabled = _dshVersions.Count > 0;
                NodeBox.IsEnabled = portable && _nodeVersions.Count > 0;
                ApplyBtn.IsEnabled = Services.InstanceActions.IsManaged(_inst);
            }
            catch (Exception ex)
            {
                SetLoading(false);
                DshHint.Text = "获取失败：" + ex.Message;
                NodeHint.Text = "";
            }
        }

        private void FillCombos()
        {
            var dshItems = new List<string> { "保持当前（" + (string.IsNullOrWhiteSpace(_currentDsh) ? "未知" : _currentDsh) + "）" };
            dshItems.AddRange(_dshVersions);
            DshBox.ItemsSource = dshItems;
            DshBox.SelectedIndex = 0;
            var nodeItems = new List<string> { "保持当前（" + (string.IsNullOrWhiteSpace(_currentNode) ? "未知" : _currentNode) + "）" };
            nodeItems.AddRange(_nodeVersions);
            NodeBox.ItemsSource = nodeItems;
            NodeBox.SelectedIndex = 0;
        }

        private async void OnRefresh(object sender, RoutedEventArgs e) => await LoadVersionsAsync();

        private void OnDrag(object sender, MouseButtonEventArgs e)
        {
            if (e.LeftButton == MouseButtonState.Pressed) DragMove();
        }

        private void OnClose(object sender, RoutedEventArgs e) => Close();

        private void OnApply(object sender, RoutedEventArgs e)
        {
            if (DshBox.SelectedIndex > 0) SelectedDsh = DshBox.SelectedItem as string;
            if (NodeBox.SelectedIndex > 0) SelectedNode = NodeBox.SelectedItem as string;
            if (string.IsNullOrWhiteSpace(SelectedDsh) && string.IsNullOrWhiteSpace(SelectedNode))
            {
                Close();
                return;
            }
            DialogResult = true;
            Close();
        }
    }
}
