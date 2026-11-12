using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Shapes;
using System.Windows.Threading;
using DshManager.Services;

namespace DshManager;

public partial class MainWindow : Window
{
    /// <summary>发现的 DSH 安装（npx 缓存 / 全局 npm / profile / PATH）。</summary>
    private List<DshInstance> _instances = new();
    private DshInstance _current;
    private DispatcherTimer _poll;
    private Popup _themePopup;
    private Popup _morePopup;

    // ---- 自定义缩放/最大化（透明窗口 + 无边框，系统不给缩放边框，只能自己做）----
    private enum EdgeZone
    {
        None, Left, Right, Top, Bottom, TopLeft, TopRight, BottomLeft, BottomRight
    }

    private const double GripSize = 8;      // 可抓取的边缘宽度（DIP）
    private EdgeZone _hotZone = EdgeZone.None;
    private EdgeZone _dragZone = EdgeZone.None;
    private bool _resizing;
    private Point _resizeStartScreen;
    private Rect _resizeStartRect;
    private bool _isMaximized;
    private Rect _restoreBounds;

    private double Dpi => VisualTreeHelper.GetDpi(this).DpiScaleX;

    /// <summary>管理器版本（取自程序集，csproj 里一处定义）。</summary>
    internal static string AppVersion
    {
        get
        {
            try
            {
                var v = typeof(MainWindow).Assembly.GetName().Version;
                return v == null ? "1.0.0" : v.ToString(3);
            }
            catch { return "1.0.0"; }
        }
    }

    private void OnLoadedResponsive(object sender, RoutedEventArgs e) => ApplyResponsive();

    /// <summary>临时诊断：把缩放相关的事件写进 %LOCALAPPDATA%\dsh-manager\ui.log。</summary>
    private static readonly bool _diagOn =
        Environment.GetEnvironmentVariable("DSH_MANAGER_DEBUG") == "1";

    /// <summary>是否正处于「拖动边缘缩放」过程中（WM_ENTERSIZEMOVE ~ WM_EXITSIZEMOVE）。</summary>
    private bool _inLiveResize;

    // 每帧都要做的重活合并到 ~16ms 一次（拖动时 WM_SIZE 可能 100+/秒，多余的丢掉）
    private DispatcherTimer _resizeThrottle;
    private bool _resizePending;
    private RectangleGeometry _shellClipGeo;
    private RectangleGeometry _contentClipGeo;
    private double _clipRadius;

    // 拖动期间暂时摘掉的软件位图效果（DropShadowEffect 每帧都要重新模糊，很贵）
    private readonly List<(UIElement El, Effect Fx)> _suspendedEffects = new();

    // 「冻结式缩放」：拖动期间内容不重排，只按固定尺寸渲染一次再整体缩放

    // 帧间隔采样：拖动一次，记录平均帧时间
    private readonly List<double> _frameGaps = new();
    private long _lastFrameTicks;

    private void ScheduleResizeWork()
    {
        _resizePending = true;
        if (_resizeThrottle == null)
        {
            _resizeThrottle = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(16) };
            _resizeThrottle.Tick += (_, _) =>
            {
                if (!_resizePending) { _resizeThrottle.Stop(); return; }
                _resizePending = false;
                var sw = System.Diagnostics.Stopwatch.StartNew();
                // 拖动中两件事都不做：
                //  - Clip 会让整棵视觉树重绘（比布局还贵）；
                //  - ApplyResponsive 会重排（卡片列数/侧栏宽度/换行）。
                // 松手时统一算一次。窗口本身是 DWM 圆角，拖动中不会露出方角。
                if (_inLiveResize) return;   // 缩放已在 SizeChanged 里按事件尺寸更新
                UpdateShellClip();
                ApplyResponsive();
                if (sw.ElapsedMilliseconds >= 8)
                    Diag("sizechange 慢 " + sw.ElapsedMilliseconds + " ms (resizing=" + _inLiveResize + ")");
            };
        }
        if (!_resizeThrottle.IsEnabled) _resizeThrottle.Start();
    }

    /// <summary>
    /// 拖动缩放开始/结束时调用：
    ///  True  → 临时摘掉视觉树里所有 Effect（阴影是软件渲染，每帧重算），图片降采样质量；
    ///  False → 原样恢复。
    /// </summary>
    private void SuspendHeavyVisuals(bool suspend)
    {
        try
        {
            if (suspend)
            {
                if (_suspendedEffects.Count > 0) return;
                SuspendEffectsRecursive(this);
                RenderOptions.SetBitmapScalingMode(this, BitmapScalingMode.Linear);
                TextOptions.SetTextRenderingMode(this, TextRenderingMode.Grayscale);
                TextOptions.SetTextFormattingMode(this, TextFormattingMode.Ideal);
                Diag("suspend 效果 " + _suspendedEffects.Count + " 个（拖动缩放期间）");
            }
            else
            {
                foreach (var (el, fx) in _suspendedEffects)
                {
                    try { el.Effect = fx; } catch { }
                }
                _suspendedEffects.Clear();
                RenderOptions.SetBitmapScalingMode(this, BitmapScalingMode.HighQuality);
                TextOptions.SetTextRenderingMode(this, TextRenderingMode.ClearType);
                TextOptions.SetTextFormattingMode(this, TextFormattingMode.Display);
            }
        }
        catch (Exception ex) { Diag("suspend 失败：" + ex.Message); }
    }

    private void SuspendEffectsRecursive(DependencyObject node)
    {
        var count = VisualTreeHelper.GetChildrenCount(node);
        for (var i = 0; i < count; i++)
        {
            var child = VisualTreeHelper.GetChild(node, i);
            if (child is UIElement el && el.Effect != null)
            {
                _suspendedEffects.Add((el, el.Effect));
                el.Effect = null;
            }
            SuspendEffectsRecursive(child);
        }
    }

    // 拖动期间的「矢量缩放」状态：内容按最后一次稳定尺寸排好版，
    // 拖动时只改 RenderTransform（WPF 会按新比例重新光栅化，是矢量缩放，不是截图）
    private ScaleTransform _liveScale;
    private Size _baseSize;
    private bool _frozen;

    /// <summary>把内容尺寸对齐到宿主 Canvas（稳定状态下才做，会触发一次布局）。</summary>
    private void SyncContentSize()
    {
        if (ContentHost == null || ShellContent == null || _frozen) return;
        var w = ContentHost.ActualWidth;
        var h = ContentHost.ActualHeight;
        if (w < 40 || h < 40) return;
        ShellContent.Width = w;
        ShellContent.Height = h;
        UpdateShellClip();   // 顺带把窗口 Region（圆角）也重新裁一次
    }

    /// <summary>
    /// 拖动开始：记下当前尺寸，装一个 ScaleTransform。
    /// 之后拖动只改 ScaleX/ScaleY —— 布局树不动，WPF 按矢量重新渲染（清晰，不糊）。
    /// </summary>
    private void BeginFrozenResize()
    {
        try
        {
            if (_frozen || ShellContent == null || ContentHost == null) return;
            var w = ShellContent.ActualWidth;
            var h = ShellContent.ActualHeight;
            if (w < 80 || h < 80) return;
            _baseSize = new Size(w, h);
            ShellContent.Width = w;      // 钉住：拖动期间不参与重新测量
            ShellContent.Height = h;
            Canvas.SetLeft(ShellContent, 0);
            Canvas.SetTop(ShellContent, 0);
            _liveScale = new ScaleTransform(1, 1);
            ShellContent.RenderTransformOrigin = new Point(0, 0);
            ShellContent.RenderTransform = _liveScale;
            _frozen = true;
            Diag("矢量缩放开始 " + Math.Round(w) + "x" + Math.Round(h));
        }
        catch (Exception ex) { Diag("矢量缩放失败：" + ex.Message); }
    }

    /// <summary>
    /// 拖动中：按拖拽方向预置的算式算缩放比例（横向只放大 X、竖向只放大 Y、斜向两者都变）。
    /// 这些算式就是「提前算好的缩放算法」，每次鼠标位置一套即可，不触发布局。
    /// </summary>
    private void UpdateFrozenScale(Size target)
    {
        if (!_frozen || _liveScale == null) return;
        try
        {
            if (target.Width <= 1 || target.Height <= 1) return;
            var sx = Math.Max(0.05, target.Width / _baseSize.Width);
            var sy = Math.Max(0.05, target.Height / _baseSize.Height);
            var z = _dragZone;
            var horizontal = z is EdgeZone.Left or EdgeZone.Right;
            var vertical = z is EdgeZone.Top or EdgeZone.Bottom;
            if (horizontal) sy = 1;                    // 只拖左右：纵向不缩放
            else if (vertical) sx = 1;                 // 只拖上下：横向不缩放
            // 斜角：四角锁比例（DoResize 已经按比例算窗口尺寸），这里两者同比例变化
            _liveScale.ScaleX = sx;
            _liveScale.ScaleY = sy;
        }
        catch { }
    }

    /// <summary>拖动结束：撤掉变换、按新尺寸真正排一次版（这次排完就是下一次拖动的基准）。</summary>
    private void EndFrozenResize()
    {
        if (!_frozen) return;
        _frozen = false;
        try
        {
            if (ShellContent != null) ShellContent.RenderTransform = null;
            _liveScale = null;
        }
        catch { }
        SyncContentSize();
        UpdateShellClip();
        ApplyResponsive();
        Diag("矢量缩放结束 " + Math.Round(ActualWidth) + "x" + Math.Round(ActualHeight));
    }

    private void StartFrameProbe()
    {
        _frameGaps.Clear();
        _lastFrameTicks = 0;
        CompositionTarget.Rendering -= OnFrameProbe;
        CompositionTarget.Rendering += OnFrameProbe;
    }

    private void OnFrameProbe(object sender, EventArgs e)
    {
        var now = System.Diagnostics.Stopwatch.GetTimestamp();
        if (_lastFrameTicks != 0)
        {
            var ms = (now - _lastFrameTicks) * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
            if (ms > 0 && ms < 500) _frameGaps.Add(ms);
        }
        _lastFrameTicks = now;
    }

    private void StopFrameProbe()
    {
        CompositionTarget.Rendering -= OnFrameProbe;
        if (_frameGaps.Count < 5) { Diag("拖拽帧采样：帧数太少（" + _frameGaps.Count + "）"); return; }
        var avg = _frameGaps.Average();
        var sorted = _frameGaps.OrderBy(x => x).ToList();
        var p95 = sorted[(int)Math.Min(sorted.Count - 1, Math.Floor(sorted.Count * 0.95))];
        var max = sorted[sorted.Count - 1];
        Diag(string.Format("拖拽帧: {0} 帧 · 平均 {1:N1} ms · p95 {2:N1} ms · 最差 {3:N1} ms · 估算 {4:N0} fps",
            _frameGaps.Count, avg, p95, max, 1000.0 / avg));
    }

    private static void Diag(string msg)
    {
        if (!_diagOn) return;
        try
        {
            var dir = System.IO.Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "dsh-manager");
            System.IO.Directory.CreateDirectory(dir);
            System.IO.File.AppendAllText(System.IO.Path.Combine(dir, "ui.log"),
                DateTime.Now.ToString("HH:mm:ss.fff ") + msg + Environment.NewLine);
        }
        catch { }
    }

    public MainWindow()
    {
        InitializeComponent();
        if (BrandVersion != null) BrandVersion.Text = "v" + AppVersion;
        Watchdog.Start();
        StartTtsWatcher();
        // 实例在 OnLoaded 里扫描（构造时还没有扫描结果，不能索引）
        Loaded += OnLoaded;
        // 拖动边缘缩放时，每个 WM_SIZE 都会触发 SizeChanged；这里只做最便宜的裁剪，
        // 重排（ApplyResponsive）等到松手（WM_EXITSIZEMOVE）再算一次，避免拖动时掉帧。
        SizeChanged += (_, e) =>
        {
            // 拖动中：用事件携带的新尺寸算缩放（此时 Window.ActualWidth 还是旧值）
            if (_inLiveResize) { UpdateFrozenScale(e.NewSize); return; }
            SyncContentSize();
            ScheduleResizeWork();
        };
        ThemeService.ThemeChanged += OnThemeChanged;
        // 最小化 / 还原 / 最大化 都会让系统丢掉窗口 Region → 补裁一次圆角
        StateChanged += (_, _) =>
        {
            Diag("state -> " + WindowState);
            ReapplyWindowRegionSoon();
        };
    }

    /// <summary>
    /// 把外壳内容裁成圆角：外壳背景和边框是圆角的，但子元素（侧栏、顶栏）会画到方角上，
    /// 于是四角露出半透明的方角（用户看到的「半透明尖角」）。
    /// 注意：必须挂在 ShellContent 自己的 SizeChanged 上——窗口 Loaded 时它可能还是 0×0，
    /// 那时候算出来的 clip 是空的，等于没裁。
    /// </summary>
    private void UpdateShellClip()
    {
        if (ShellContent == null) return;
        var r = 26.0;
        try { if (TryFindResource("AppRadiusValue") is double d) r = d; } catch { }
        var w = ShellContent.ActualWidth;
        var h = ShellContent.ActualHeight;
        if (w <= 0 || h <= 0) return;
        // 窗口四角原本靠 DWM，但 DONOTROUND + 不透明背景会露出「方角黑块」，
        // 所以这里自己裁圆角；只在稳定尺寸下更新（拖动中不动，免得每帧重绘整棵树）。
        if (_contentClipGeo == null || Math.Abs(_clipRadius - r) > 0.01)
        {
            _clipRadius = r;
            _contentClipGeo = new RectangleGeometry(new Rect(0, 0, w, h), r, r);
            ShellContent.Clip = _contentClipGeo;
        }
        else _contentClipGeo.Rect = new Rect(0, 0, w, h);
        if (Shell != null && Shell.ActualWidth > 0 && Shell.ActualHeight > 0)
        {
            if (_shellClipGeo == null || Math.Abs(_clipRadius - r) > 0.01)
            {
                _shellClipGeo = new RectangleGeometry(
                    new Rect(0, 0, Shell.ActualWidth, Shell.ActualHeight), r, r);
                Shell.Clip = _shellClipGeo;
            }
            else _shellClipGeo.Rect = new Rect(0, 0, Shell.ActualWidth, Shell.ActualHeight);
        }
        ApplyWindowRegion(r);
    }

    [DllImport("user32.dll")]
    private static extern int SetWindowRgn(IntPtr hWnd, IntPtr hRgn, bool redraw);

    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateRoundRectRgn(int left, int top, int right, int bottom, int w, int h);

    /// <summary>
    /// 用窗口 Region 把整窗裁成圆角：半径用**设计值**（AppRadiusValue），
    /// 这样外缘圆角与内部内容圆角完全一致；DWM 自己的圆角已经关掉，不会再出现「一大一小两个弧度」。
    /// </summary>
    /// <summary>
    /// 最小化 → 还原、最大化 → 还原之后，窗口的 Region 会被系统丢掉（方角又回来了）。
    /// 状态变化后补两次：立刻一次 + 稍后一次（系统可能在我们之后才重置）。
    /// </summary>
    private void ReapplyWindowRegionSoon()
    {
        try
        {
            var r = 26.0;
            try { if (TryFindResource("AppRadiusValue") is double d) r = d; } catch { }
            ApplyWindowRegion(r);
            var t = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(120) };
            t.Tick += (_, _) =>
            {
                t.Stop();
                var rr = 26.0;
                try { if (TryFindResource("AppRadiusValue") is double d2) rr = d2; } catch { }
                ApplyWindowRegion(rr);
            };
            t.Start();
        }
        catch { }
    }

    private void ApplyWindowRegion(double radiusDip)
    {
        try
        {
            var hwnd = new WindowInteropHelper(this).Handle;
            if (hwnd == IntPtr.Zero) return;
            var dpi = VisualTreeHelper.GetDpi(this).DpiScaleX;
            var w = (int)Math.Round(ActualWidth * dpi);
            var h = (int)Math.Round(ActualHeight * dpi);
            if (w <= 1 || h <= 1) return;
            var r = (int)Math.Round(radiusDip * dpi * 2);   // CreateRoundRectRgn 的椭圆宽高 = 直径
            var hRgn = CreateRoundRectRgn(0, 0, w + 1, h + 1, r, r);
            if (hRgn != IntPtr.Zero)
            {
                var ok = SetWindowRgn(hwnd, hRgn, true);
                Diag("window region " + w + "x" + h + " r=" + (r / 2) + " ok=" + ok);
            }   // 成功后区域归系统所有，不要删
        }
        catch { }
    }

    /// <summary>
    /// 响应式布局：窗口可以缩到 1/4 屏（720×450）。
    ///  - 宽度 &lt; 1060：实例卡/快捷控制卡上下堆叠（侧栏也收窄）
    ///  - 宽度 &lt; 900：侧栏 180，内容边距收紧
    ///  - 高度 &lt; 620：隐藏页头描述与页脚
    ///  - 常用功能按可用宽度自动 4/3/2 列
    /// </summary>
    private void ApplyResponsive()
    {
        if (Quick1 == null || OverviewGrid == null) return;
        var w = ActualWidth;
        var h = ActualHeight;
        var narrow = w < 1060;
        var tight = w < 900;
        var shortH = h < 620;

        try
        {
            SidebarCol.Width = new GridLength(tight ? 180 : (narrow ? 220 : 248));
            ContentScroll.Padding = tight ? new Thickness(18, 16, 18, 12)
                                          : new Thickness(30, 25, 30, 15);
            PageDesc.Visibility = shortH ? Visibility.Collapsed : Visibility.Visible;
            PageFooter.Visibility = shortH ? Visibility.Collapsed : Visibility.Visible;

            // 概览两卡：窄屏上下堆叠
            if (narrow)
            {
                OverviewGrid.ColumnDefinitions.Clear();
                OverviewGrid.ColumnDefinitions.Add(new ColumnDefinition());
                if (OverviewGrid.RowDefinitions.Count == 0)
                {
                    OverviewGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    OverviewGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                }
                Grid.SetColumn(InstanceCard, 0);
                Grid.SetColumnSpan(InstanceCard, 1);
                Grid.SetRow(InstanceCard, 0);
                Grid.SetColumn(ControlCard, 0);
                Grid.SetColumnSpan(ControlCard, 1);
                Grid.SetRow(ControlCard, 1);
                ControlCard.Margin = new Thickness(0, 14, 0, 0);
            }
            else
            {
                OverviewGrid.RowDefinitions.Clear();
                OverviewGrid.ColumnDefinitions.Clear();
                OverviewGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1.65, GridUnitType.Star) });
                OverviewGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(16) });
                OverviewGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                Grid.SetRow(InstanceCard, 0);
                Grid.SetRow(ControlCard, 0);
                Grid.SetColumn(InstanceCard, 0);
                Grid.SetColumn(ControlCard, 2);
                Grid.SetColumnSpan(InstanceCard, 1);
                Grid.SetColumnSpan(ControlCard, 1);
                ControlCard.Margin = new Thickness(0);
            }

            // 常用功能：按可用宽度决定列数，WrapPanel 自动换行
            var side = tight ? 180 : (narrow ? 220 : 248);
            var pad = tight ? 36 : 60;
            var avail = Math.Max(300, w - side - pad);
            // 用 UniformGrid：只设列数，卡片宽度由 Grid 均分，**每行必然填满整行**。
            var cols = avail >= 900 ? 4 : (avail >= 480 ? 2 : 1);
            var gap = 11.0;
            if (QuickGrid != null) { QuickGrid.Columns = cols; QuickGrid.Rows = (int)Math.Ceiling(4.0 / cols); }
            var cards = new[] { Quick1, Quick2, Quick3, Quick4 };
            for (var i = 0; i < cards.Length; i++)
            {
                if (cards[i] == null) continue;
                cards[i].Width = double.NaN;
                cards[i].HorizontalAlignment = HorizontalAlignment.Stretch;
                cards[i].Margin = new Thickness(0, 0, (i % cols == cols - 1) ? 0 : gap, gap);
            }
        }
        catch { }
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        ApplyRoundedCorners();
        SyncContentSize();
        UpdateShellClip();
        _ = ReloadInstancesAsync();
        _poll = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2.5) };
        _poll.Tick += (_, _) => PollCurrent();
        _poll.Start();
        RefreshThemeUi();
        if (ShellContent != null)
        {
            ShellContent.SizeChanged += (_, _) => UpdateShellClip();
        }
        UpdateShellClip();
        RuntimeLine.Text = ".NET " + Environment.Version.Major + " · WPF";
        try { Diag("WPF 渲染层 Tier=" + (RenderCapability.Tier >> 16)); } catch { }
        FooterPath.Text = "实例根目录 · " + RootDir;
        ApplyResponsive();
        // 调试用：直接打开「更新 dsh」窗口（方便截图验收）
        if (Environment.GetCommandLineArgs().Any(a => a == "--shot-window"))
        {
            var tw = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(700) };
            var tn2 = 0;
            tw.Tick += (_, _) =>
            {
                if (++tn2 > 30) { tw.Stop(); return; }
                if (_current == null) return;
                tw.Stop();
                OnOpenWindow(this, new RoutedEventArgs());
            };
            tw.Start();
        }
        if (Environment.GetCommandLineArgs().Any(a => a == "--shot-token"))
        {
            var tk = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(600) };
            var tn = 0;
            tk.Tick += (_, _) =>
            {
                if (++tn > 30) { tk.Stop(); return; }
                if (_current == null) return;
                tk.Stop();
                OnShowToken();
            };
            tk.Start();
        }
        if (Environment.GetCommandLineArgs().Any(a => a == "--shot-update"))
        {
            // 等实例扫描完成（_current 有值）再打开，否则会直接提示"先选一个实例"
            var t = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(600) };
            var tries = 0;
            t.Tick += (_, _) =>
            {
                if (++tries > 30) { t.Stop(); return; }
                if (_current == null) return;
                t.Stop();
                CheckUpdateAsync();
            };
            t.Start();
        }
    }

    private static string RootDir =>
        System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            "Programs");

    // ---------------------------------------------------------------- 主题
    private void OnThemeChanged()
    {
        Dispatcher.BeginInvoke(new Action(() => { RefreshThemeUi(); ReapplyWindowRegionSoon(); }));
    }

    private void RefreshThemeUi()
    {
        if (ThemeName != null)
            ThemeName.Text = ThemeService.Label;
        if (!_isMaximized && Shell != null)
            Shell.ClearValue(Border.CornerRadiusProperty);   // 交还给 DynamicResource 里的 AppRadius
        UpdateShellClip();
        var night = ThemeService.Mode == "night";
        if (ModeThumb != null)
        {
            ModeThumb.HorizontalAlignment = HorizontalAlignment.Left;
            ModeThumb.Margin = night ? new Thickness(27, 0, 0, 0) : new Thickness(3, 0, 0, 0);
        }
        if (SunIcon != null && MoonIcon != null)
        {
            SunIcon.Opacity = night ? 0.5 : 1;
            MoonIcon.Opacity = night ? 1 : 0.55;
        }
    }

    private void OnToggleMode(object sender, MouseButtonEventArgs e)
    {
        ThemeService.ToggleMode();
    }

    private void OnThemeTrigger(object sender, RoutedEventArgs e)
    {
        if (_themePopup != null && _themePopup.IsOpen)
        {
            _themePopup.IsOpen = false;
            return;
        }

        var panel = new StackPanel { Margin = new Thickness(7) };
        panel.Children.Add(new TextBlock
        {
            Text = "选择界面主题",
            FontSize = 10,
            Margin = new Thickness(9, 7, 9, 9),
            Foreground = (Brush)FindResource("Muted"),
        });

        foreach (var (id, label, hint, swatch) in ThemeService.Themes)
        {
            var row = new Grid { Height = 38, Margin = new Thickness(0, 1, 0, 0) };
            var sw = new Border
            {
                Width = 12, Height = 12, CornerRadius = new CornerRadius(4),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString(swatch)),
                VerticalAlignment = VerticalAlignment.Center,
                HorizontalAlignment = HorizontalAlignment.Left,
                Margin = new Thickness(9, 0, 0, 0),
            };
            var name = new TextBlock
            {
                Text = label, FontSize = 11, Margin = new Thickness(30, 0, 0, 0),
                VerticalAlignment = VerticalAlignment.Center,
                Foreground = (Brush)FindResource("Text"),
            };
            var sub = new TextBlock
            {
                Text = hint, FontSize = 9, VerticalAlignment = VerticalAlignment.Center,
                HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 0, 9, 0),
                Foreground = (Brush)FindResource("Muted"),
            };
            row.Children.Add(sw);
            row.Children.Add(name);
            row.Children.Add(sub);

            var btn = new Button
            {
                Content = row,
                Background = id == ThemeService.Theme ? (Brush)FindResource("AccentSoft") : Brushes.Transparent,
                BorderThickness = new Thickness(0),
                Cursor = Cursors.Hand,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
            };
            var template = new ControlTemplate(typeof(Button));
            var border = new FrameworkElementFactory(typeof(Border));
            border.SetValue(Border.CornerRadiusProperty, new CornerRadius(9));
            border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Button.BackgroundProperty));
            var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
            presenter.SetValue(HorizontalAlignmentProperty, HorizontalAlignment.Stretch);
            presenter.SetValue(VerticalAlignmentProperty, VerticalAlignment.Center);
            border.AppendChild(presenter);
            template.VisualTree = border;
            btn.Template = template;
            btn.Click += (_, _) =>
            {
                ThemeService.SetTheme(id);
                _themePopup.IsOpen = false;
            };
            panel.Children.Add(btn);
        }

        var card = new Border
        {
            Width = 230,
            Padding = new Thickness(7),
            CornerRadius = new CornerRadius(15),
            Background = (Brush)FindResource("CardSolid"),
            BorderBrush = (Brush)FindResource("Border"),
            BorderThickness = new Thickness(1),
            Effect = new DropShadowEffect
            {
                BlurRadius = 45, ShadowDepth = 18, Direction = 270, Opacity = 0.18, Color = Colors.Black,
            },
            Child = panel,
        };

        _themePopup = new Popup
        {
            PlacementTarget = ThemeTrigger,
            Placement = PlacementMode.Bottom,
            StaysOpen = false,
            AllowsTransparency = true,
            VerticalOffset = 6,
            HorizontalOffset = 0,
            Child = card,
        };
        _themePopup.IsOpen = true;
    }

    // ---------------------------------------------------------------- 实例
    /// <summary>重新扫描本机 DSH 安装。</summary>
    /// <summary>扫描 + 反查运行状态（纯数据，可在后台线程跑）。</summary>
    private static List<DshInstance> ScanInstances()
    {
        var scanned = DshDiscovery.Scan().ToList();
        DshDiscovery.AttachRunning(scanned);      // 反查「现在真正在跑的是哪个」
        DshDiscovery.ApplyRegistryPorts(scanned); // 管理器创建的实例用登记过的端口
        return scanned
            .OrderByDescending(i => i.Running)
            .ThenBy(i => i.SortKey)
            .ToList();
    }

    /// <summary>把结果贴到界面上（必须在 UI 线程调用）。</summary>
    private void ApplyInstances(List<DshInstance> instances)
    {
        _instances = instances;
        _current = _instances.FirstOrDefault();
        BuildInstanceList();
        if (_current != null)
        {
            ShowInstance(_current);
            RefreshLogs(_current);
        }
        else ShowEmptyState();
    }

    private void ReloadInstances() => ApplyInstances(ScanInstances());

    /// <summary>
    /// 首次加载：窗口先画出来，扫描丢到后台线程再回填。
    /// 之前是在 Loaded 里同步扫（要起 powershell + netstat），窗口出来但几秒内点不动。
    /// </summary>
    private async System.Threading.Tasks.Task ReloadInstancesAsync()
    {
        var sw = System.Diagnostics.Stopwatch.StartNew();
        try
        {
            var list = await System.Threading.Tasks.Task.Run(() => ScanInstances());
            Diag("scan " + sw.ElapsedMilliseconds + " ms, " + list.Count + " 个实例");
            ApplyInstances(list);
            Diag("apply 完成 " + sw.ElapsedMilliseconds + " ms");
        }
        catch (Exception ex) { Diag("首次扫描失败：" + ex); }
    }

    private void ShowEmptyState()
    {
        InstanceTitle.Text = "未发现 DSH 安装";
        AvatarText.Text = "?";
        InstallPath.Text = "扫描位置：npx 缓存 / %APPDATA%\\npm / %DSH_HOME%\\profiles / PATH";
        DshVersion.Text = "—";
        NodeVersion.Text = "—";
        PortValue.Text = "—";
        PidValue.Text = "—";
        RunState.Text = "未安装";
        RunState.Foreground = (Brush)FindResource("Muted");
        if (SvcState != null) { SvcState.Text = "未安装"; SvcState.Foreground = (Brush)FindResource("Muted"); }
        if (SvcDot != null) SvcDot.Background = (Brush)FindResource("Subtle");
        StatusBadgeText.Text = "未安装";
        if (StatusBadgeDot != null) StatusBadgeDot.Background = (Brush)FindResource("Subtle");
        StatusBadge.Background = (Brush)FindResource("AccentSoft");
        StatusBadgeText.Foreground = (Brush)FindResource("Muted");
        LogBody.Children.Clear();
        LogCount.Text = "0";
    }

    private static string InitialsFor(DshInstance inst)
    {
        var name = inst.Source switch
        {
            "npx 缓存" => "NPX",
            "全局安装" => "GLB",
            "profile" => "PRF",
            "PATH" => "PTH",
            _ => "DSH",
        };
        return name;
    }

    private void PollCurrent()
    {
        if (_current == null) return;
        DshDiscovery.Probe(_current);
        ShowInstance(_current);
        RefreshLogs(_current);
        BuildInstanceList();
    }

    private void RefreshLogs(DshInstance inst)
    {
        // 「最近日志」只显示最新 15 条（完整日志走「查看完整日志 →」）
        var text = DshHost.Tail(inst, 15);
        LogBody.Children.Clear();
        if (string.IsNullOrWhiteSpace(text))
        {
            LogCount.Text = "0";
            LogBody.Children.Add(new TextBlock
            {
                Text = "（还没有日志：服务由管理器启动后这里会实时显示）",
                FontSize = 8.5, Margin = new Thickness(0, 6, 0, 6),
                Foreground = (Brush)FindResource("Muted"),
            });
            return;
        }
        var lines = text.Split('\n');
        foreach (var raw in lines)
        {
            var line = raw.TrimEnd();
            if (line.Length == 0) continue;
            AddLogLine(DateTime.Now.ToString("HH:mm:ss"), "信息", line);
        }
        LogCount.Text = lines.Length.ToString();
    }

    private void AddLogLine(string time, string level, string text)
    {
        var grid = new Grid { Height = 27, Margin = new Thickness(0, 1, 0, 0) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(70) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

        var t = new TextBlock
        {
            Text = time, FontSize = 8.5, FontFamily = (FontFamily)FindResource("MonoFont"),
            Foreground = (Brush)FindResource("Subtle"), VerticalAlignment = VerticalAlignment.Center,
        };
        var levelText = new TextBlock
        {
            Text = level, FontSize = 7.5, FontWeight = FontWeights.SemiBold,
            HorizontalAlignment = HorizontalAlignment.Center,
            Foreground = (Brush)FindResource("Accent"),
        };
        var levelBorder = new Border
        {
            CornerRadius = new CornerRadius(4), Padding = new Thickness(4, 2, 4, 2),
            VerticalAlignment = VerticalAlignment.Center, Child = levelText,
            MinWidth = 29, Margin = new Thickness(0, 0, 11, 0),
            Background = (Brush)FindResource("AccentSoft"),
        };
        var msg = new TextBlock
        {
            Text = text, FontSize = 8.5, VerticalAlignment = VerticalAlignment.Center,
            Foreground = (Brush)FindResource("Text"), TextTrimming = TextTrimming.CharacterEllipsis,
        };
        Grid.SetColumn(t, 0);
        Grid.SetColumn(levelBorder, 1);
        Grid.SetColumn(msg, 2);
        grid.Children.Add(t);
        grid.Children.Add(levelBorder);
        grid.Children.Add(msg);
        LogBody.Children.Add(grid);
    }

    private void BuildInstanceList()
    {
        InstanceList.Children.Clear();
        foreach (var inst in _instances)
        {
            var grid = new Grid { Margin = new Thickness(10, 8, 10, 8) };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            var avatar = new Border
            {
                Width = 34, Height = 34, CornerRadius = new CornerRadius(10),
                Background = (Brush)FindResource(inst == _current ? "Accent" : "AccentSoft"),
                VerticalAlignment = VerticalAlignment.Center,
            };
            var initials = new TextBlock
            {
                Text = InitialsFor(inst), FontSize = 10, FontWeight = FontWeights.Bold,
                Foreground = (Brush)FindResource(inst == _current ? "OnAccent" : "Accent"),
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
            };
            avatar.Child = initials;

            var copy = new StackPanel { Margin = new Thickness(10, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center };
            copy.Children.Add(new TextBlock
            {
                Text = inst.Label, FontSize = 11.5, FontWeight = FontWeights.SemiBold,
                Foreground = (Brush)FindResource("Text"), TextTrimming = TextTrimming.CharacterEllipsis,
            });
            var subtitle = "dsh " + (string.IsNullOrEmpty(inst.DshVersion) ? "?" : inst.DshVersion)
                           + " · " + inst.Source;
            if (inst.Running && inst.Pid > 0) subtitle += " · PID " + inst.Pid;
            copy.Children.Add(new TextBlock
            {
                Text = subtitle, FontSize = 10, Margin = new Thickness(0, 4, 0, 0),
                Foreground = (Brush)FindResource(inst.Running ? "Accent" : "Muted"),
            });

            var dot = new Border
            {
                Width = 6, Height = 6, CornerRadius = new CornerRadius(3),
                VerticalAlignment = VerticalAlignment.Center,
                Background = (Brush)FindResource(inst.Running ? "Success" : "Subtle"),
            };

            Grid.SetColumn(avatar, 0);
            Grid.SetColumn(copy, 1);
            Grid.SetColumn(dot, 2);
            grid.Children.Add(avatar);
            grid.Children.Add(copy);
            grid.Children.Add(dot);

            var btn = new Button
            {
                Height = 61, Content = grid, Cursor = Cursors.Hand,
                Background = inst == _current ? (Brush)FindResource("Hover") : Brushes.Transparent,
                BorderThickness = new Thickness(0),
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
            };
            var tmpl = new ControlTemplate(typeof(Button));
            var bd = new FrameworkElementFactory(typeof(Border));
            bd.SetValue(Border.CornerRadiusProperty, new CornerRadius(13));
            bd.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Button.BackgroundProperty));
            var cp = new FrameworkElementFactory(typeof(ContentPresenter));
            cp.SetValue(VerticalAlignmentProperty, VerticalAlignment.Center);
            bd.AppendChild(cp);
            tmpl.VisualTree = bd;
            btn.Template = tmpl;
            var captured = inst;
            btn.Click += (_, _) =>
            {
                _current = captured;
                BuildInstanceList();
                ShowInstance(captured);
            };
            InstanceList.Children.Add(btn);
        }
        InstanceCount.Text = _instances.Count.ToString();
    }

    private void ShowInstance(DshInstance inst)
    {
        InstanceTitle.Text = inst.Label;
        AvatarText.Text = InitialsFor(inst);
        InstallPath.Text = inst.Entry;
        DshVersion.Text = string.IsNullOrEmpty(inst.DshVersion) ? "?" : inst.DshVersion;
        NodeVersion.Text = string.IsNullOrEmpty(inst.NodeVersion) ? "?" : inst.NodeVersion;
        PortValue.Text = inst.Port.ToString();
        PidValue.Text = inst.Pid > 0 ? inst.Pid.ToString() : "—";
        RunState.Text = inst.Running ? "运行中" : "未运行";
        RunState.Foreground = (Brush)FindResource(inst.Running ? "Success" : "Muted");
        // 右上角那颗「服务正常」也要跟着实例真实状态走（未运行时不能还显示绿色正常）
        if (SvcState != null)
        {
            SvcState.Text = inst.Running ? "服务正常" : "未运行";
            SvcState.Foreground = (Brush)FindResource(inst.Running ? "Success" : "Muted");
        }
        if (SvcDot != null)
            SvcDot.Background = (Brush)FindResource(inst.Running ? "Success" : "Subtle");
        // 未运行时那颗按钮应该是「启动」而不是「停止」
        if (StopBtn != null)
        {
            StopLabel.Text = inst.Running ? "停止" : "启动";
            StopBtn.Background = (Brush)FindResource(inst.Running ? "DangerSoft" : "SuccessSoft");
            StopBtn.Foreground = (Brush)FindResource(inst.Running ? "Danger" : "Success");
            if (StopIcon != null) StopIcon.Stroke = (Brush)FindResource(inst.Running ? "Danger" : "Success");
        }
        StatusBadgeText.Text = inst.Running ? "运行中" : "未运行";
        if (StatusBadgeDot != null)
            StatusBadgeDot.Background = (Brush)FindResource(inst.Running ? "Success" : "Subtle");
        StatusBadge.Background = (Brush)FindResource(inst.Running ? "SuccessSoft" : "AccentSoft");
        StatusBadgeText.Foreground = (Brush)FindResource(inst.Running ? "Success" : "Muted");
    }

    private void BuildSampleLogs()
    {
        LogBody.Children.Clear();
        var items = new[]
        {
            ("14:32:08", "成功", "已把现有窗口提到前台", " (PID 87972)"),
            ("14:31:56", "信息", "窗口程序已更新，重建窗口后新功能即可生效", ""),
            ("14:31:42", "系统", "实例服务运行正常，监听端口 ", "3080"),
        };
        foreach (var (time, level, text, tail) in items)
        {
            var grid = new Grid { Height = 27, Margin = new Thickness(0, 1, 0, 0) };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(70) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            var t = new TextBlock
            {
                Text = time, FontSize = 8.5, FontFamily = (FontFamily)FindResource("MonoFont"),
                Foreground = (Brush)FindResource("Subtle"), VerticalAlignment = VerticalAlignment.Center,
            };
            var levelText = new TextBlock
            {
                Text = level, FontSize = 7.5, FontWeight = FontWeights.SemiBold,
                HorizontalAlignment = HorizontalAlignment.Center,
            };
            var levelBorder = new Border
            {
                CornerRadius = new CornerRadius(4), Padding = new Thickness(4, 2, 4, 2),
                VerticalAlignment = VerticalAlignment.Center, Child = levelText,
                MinWidth = 29, Margin = new Thickness(0, 0, 11, 0),
            };
            switch (level)
            {
                case "成功":
                    levelText.Foreground = (Brush)FindResource("Success");
                    levelBorder.Background = (Brush)FindResource("SuccessSoft");
                    break;
                case "信息":
                    levelText.Foreground = (Brush)FindResource("Accent");
                    levelBorder.Background = (Brush)FindResource("AccentSoft");
                    break;
                default:
                    levelText.Foreground = (Brush)FindResource("Muted");
                    levelBorder.Background = (Brush)FindResource("AccentSoft");
                    break;
            }
            var msg = new TextBlock
            {
                FontSize = 8.5, VerticalAlignment = VerticalAlignment.Center,
                Foreground = (Brush)FindResource("Text"), TextTrimming = TextTrimming.CharacterEllipsis,
            };
            msg.Inlines.Add(new System.Windows.Documents.Run(text));
            if (!string.IsNullOrEmpty(tail))
                msg.Inlines.Add(new System.Windows.Documents.Run(tail)
                {
                    Foreground = (Brush)FindResource("Muted"),
                });

            Grid.SetColumn(t, 0);
            Grid.SetColumn(levelBorder, 1);
            Grid.SetColumn(msg, 2);
            grid.Children.Add(t);
            grid.Children.Add(levelBorder);
            grid.Children.Add(msg);
            LogBody.Children.Add(grid);
        }
        LogCount.Text = items.Length.ToString();
    }


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

    private IntPtr _winHwnd;
    private int _hitZone;
    private bool _nativeResize;
    private POINT _nativeStartMouse;

    [StructLayout(LayoutKind.Sequential)]
    private struct RECTW { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr h, out RECTW r);

    private RECTW _nativeStartPhys;

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
        // 0x0231 = WM_ENTERSIZEMOVE, 0x0232 = WM_EXITSIZEMOVE
        if (msg == 0x0231)   // WM_ENTERSIZEMOVE
        {
            if (_resizing) return WndProcCore(hwnd, msg, wParam, lParam, ref handled);  // 自绘拖边已在处理
            _inLiveResize = true;
            Diag("ENTER_SIZEMOVE");
            SuspendHeavyVisuals(true);
            BeginFrozenResize();
            StartFrameProbe();
        }
        else if (msg == 0x0232)   // WM_EXITSIZEMOVE
        {
            if (_resizing || !_inLiveResize) return WndProcCore(hwnd, msg, wParam, lParam, ref handled);
            _inLiveResize = false;
            Diag("EXIT_SIZEMOVE");
            StopFrameProbe();
            EndFrozenResize();
            UpdateShellClip();
            ApplyResponsive();
            SuspendHeavyVisuals(false);
        }
        return WndProcCore(hwnd, msg, wParam, lParam, ref handled);
    }

    private IntPtr WndProcCore(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
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
                GetWindowRect(hwnd, out _nativeStartPhys);
                Diag($"resize-start zone={zone} rect=({_nativeStartPhys.Left},{_nativeStartPhys.Top})" +
                     $"-({_nativeStartPhys.Right},{_nativeStartPhys.Bottom})");
                _nativeResize = true;
                SetCapture(hwnd);
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
    }


    // ---------------------------------------------------------------- 缩放 / 拖动 / 圆角
    /// <summary>按窗口内坐标判断落在哪条边/哪个角上（只在窗口可见外壳边缘的 8px 内）。</summary>
    private EdgeZone ZoneAt(Point p)
    {
        if (_isMaximized) return EdgeZone.None;
        // 外壳相对窗口有 14px 透明外沿（留给投影），边缘区从外壳本身算起
        var inset = Shell.Margin.Left;
        var shellRect = new Rect(inset, inset,
            Math.Max(0, ActualWidth - inset * 2), Math.Max(0, ActualHeight - inset * 2));
        if (!shellRect.Contains(p)) return EdgeZone.None;

        var nearL = p.X <= shellRect.Left + GripSize;
        var nearR = p.X >= shellRect.Right - GripSize;
        var nearT = p.Y <= shellRect.Top + GripSize;
        var nearB = p.Y >= shellRect.Bottom - GripSize;
        return (nearL, nearR, nearT, nearB) switch
        {
            (true, _, true, _) => EdgeZone.TopLeft,
            (_, true, true, _) => EdgeZone.TopRight,
            (true, _, _, true) => EdgeZone.BottomLeft,
            (_, true, _, true) => EdgeZone.BottomRight,
            (true, _, _, _) => EdgeZone.Left,
            (_, true, _, _) => EdgeZone.Right,
            (_, _, true, _) => EdgeZone.Top,
            (_, _, _, true) => EdgeZone.Bottom,
            _ => EdgeZone.None,
        };
    }

    private static Cursor CursorFor(EdgeZone zone) => zone switch
    {
        EdgeZone.Left or EdgeZone.Right => Cursors.SizeWE,
        EdgeZone.Top or EdgeZone.Bottom => Cursors.SizeNS,
        EdgeZone.TopLeft or EdgeZone.BottomRight => Cursors.SizeNWSE,
        EdgeZone.TopRight or EdgeZone.BottomLeft => Cursors.SizeNESW,
        _ => null,
    };

    private void OnWindowMouseMove(object sender, MouseEventArgs e)
    {
        var p = e.GetPosition(this);
        if (_resizing)
        {
            DoResize(e);
            return;
        }
        var zone = ZoneAt(p);
        if (zone != _hotZone)
        {
            _hotZone = zone;
            Cursor = CursorFor(zone) ?? Cursors.Arrow;
        }
    }

    private void OnWindowMouseUp(object sender, MouseButtonEventArgs e)
    {
        EndResize();
    }

    private void OnLostCapture(object sender, MouseEventArgs e)
    {
        EndResize();
    }

    /// <summary>结束缩放：无论松手、丢捕获还是 Esc，都把状态收干净。</summary>
    private void EndResize()
    {
        Diag($"end-resize resizing={_resizing}");
        if (!_resizing) return;
        _resizing = false;
        _dragZone = EdgeZone.None;
        if (_inLiveResize)
        {
            _inLiveResize = false;
            StopFrameProbe();
            EndFrozenResize();
            UpdateShellClip();
            ApplyResponsive();
            SuspendHeavyVisuals(false);
        }
        if (IsMouseCaptured) ReleaseMouseCapture();
        Cursor = Cursors.Arrow;
    }

    private void OnWindowMouseLeave(object sender, MouseEventArgs e)
    {
        if (_resizing) return;
        _hotZone = EdgeZone.None;
        Cursor = Cursors.Arrow;
    }

    /// <summary>开始从某条边缩放（鼠标已在窗口上按下）。</summary>
    private void BeginResize(EdgeZone zone)
    {
        Diag($"begin-resize zone={zone}");
        _resizing = true;
        _dragZone = zone;
        // 这个管理器用的是**自己写的拖边缩放**（不走系统的 WM_ENTERSIZEMOVE），
        // 所以冻结/降级必须挂在这里，否则真实拖拽时根本不会触发（之前就是这样漏的）。
        _inLiveResize = true;
        SuspendHeavyVisuals(true);
        BeginFrozenResize();
        StartFrameProbe();
        _resizeStartScreen = PointToScreen(Mouse.GetPosition(this));
        _resizeStartRect = new Rect(Left, Top, ActualWidth, ActualHeight);
        CaptureMouse();
    }

    private void DoResize(MouseEventArgs e)
    {
        if (_dragZone == EdgeZone.None) return;
        Diag($"resize-move zone={_dragZone} size={ActualWidth:F0}x{ActualHeight:F0}");
        var now = PointToScreen(e.GetPosition(this));
        var scale = Dpi;
        var dx = (now.X - _resizeStartScreen.X) / scale;
        var dy = (now.Y - _resizeStartScreen.Y) / scale;
        var r = _resizeStartRect;

        var left = r.Left;
        var top = r.Top;
        var width = r.Width;
        var height = r.Height;

        var z = _dragZone;
        if (z is EdgeZone.Left or EdgeZone.TopLeft or EdgeZone.BottomLeft)
        {
            var newLeft = Math.Min(r.Left + dx, r.Right - MinWidth);
            width = r.Right - newLeft;
            left = newLeft;
        }
        if (z is EdgeZone.Right or EdgeZone.TopRight or EdgeZone.BottomRight)
            width = Math.Max(MinWidth, r.Width + dx);
        if (z is EdgeZone.Top or EdgeZone.TopLeft or EdgeZone.TopRight)
        {
            var newTop = Math.Min(r.Top + dy, r.Bottom - MinHeight);
            height = r.Bottom - newTop;
            top = newTop;
        }
        if (z is EdgeZone.Bottom or EdgeZone.BottomLeft or EdgeZone.BottomRight)
            height = Math.Max(MinHeight, r.Height + dy);

        // 四角：锁住当前宽高比（横向/竖向各取变化更大的那一侧作为主导）
        var isCorner = z is EdgeZone.TopLeft or EdgeZone.TopRight or EdgeZone.BottomLeft or EdgeZone.BottomRight;
        if (isCorner && r.Width > 1 && r.Height > 1)
        {
            var ratio = r.Width / r.Height;
            var byW = Math.Max(MinWidth, width);
            var byH = byW / ratio;
            if (byH < MinHeight) { byH = MinHeight; byW = byH * ratio; }
            width = byW;
            height = byH;
            if (z is EdgeZone.Left or EdgeZone.TopLeft or EdgeZone.BottomLeft) left = r.Right - width;
            if (z is EdgeZone.Top or EdgeZone.TopLeft or EdgeZone.TopRight) top = r.Bottom - height;
        }

        Left = left;
        Top = top;
        Width = width;
        Height = height;
    }

    private void ToggleMaximize()
    {
        var wa = SystemParameters.WorkArea;
        if (!_isMaximized)
        {
            _restoreBounds = new Rect(Left, Top, ActualWidth, ActualHeight);
            _isMaximized = true;
            // 不用 WindowState.Maximized：透明窗口最大化会盖住任务栏，这里按工作区手动铺
            Left = wa.Left;
            Top = wa.Top;
            Width = wa.Width;
            Height = wa.Height;
            Shell.Margin = new Thickness(0);
            Shell.CornerRadius = new CornerRadius(0);
            Dispatcher.BeginInvoke(new Action(ReapplyWindowRegionSoon),
                System.Windows.Threading.DispatcherPriority.Loaded);
        }
        else
        {
            _isMaximized = false;
            Shell.Margin = new Thickness(0);
            Shell.CornerRadius = (CornerRadius)FindResource("AppRadius");
            Dispatcher.BeginInvoke(new Action(ReapplyWindowRegionSoon),
                System.Windows.Threading.DispatcherPriority.Loaded);
            Left = _restoreBounds.Left;
            Top = _restoreBounds.Top;
            Width = _restoreBounds.Width;
            Height = _restoreBounds.Height;
        }
        UpdateShellClip();
    }

    private void OnMinimize(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void OnMaximize(object sender, RoutedEventArgs e) => ToggleMaximize();

    private void OnClose(object sender, RoutedEventArgs e)
    {
        // 点 X = 收进托盘（和旧桌面版一致），真正退出走托盘菜单
        var app = (App)Application.Current;
        if (app.Quitting) { Close(); return; }
        Hide();
    }

    private void OnWindowDrag(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Left) return;
        for (var d = e.OriginalSource as DependencyObject; d != null; d = VisualTreeHelper.GetParent(d))
        {
            if (d is Button || d is TextBox) return;
        }
        // 边缘交给 Win32 的 WM_NCHITTEST 缩放（见 WndProc），这里只管拖动
        var pos = e.GetPosition(this);
        Diag($"down at ({pos.X:F0},{pos.Y:F0}) size={ActualWidth:F0}x{ActualHeight:F0}");
        if (e.ClickCount == 2)
        {
            ToggleMaximize();
            return;
        }
        try { DragMove(); } catch { }
    }

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    private void ApplyRoundedCorners()
    {
        try
        {
            var hwnd = new WindowInteropHelper(this).Handle;
            // 窗口自己已经用 26px 圆角 + 1px 边框画了唯一一条边缘，这里必须让 DWM 不要再圆一次，
            // 否则会出现「系统圆角 + 自绘圆角」两条边（用户截图里看到的就是边缘发虚的双线）。
            var preference = 1; // DWMWCP_DONOTROUND：圆角由我们自己用窗口 Region 裁，才能和设计弧度一致
            DwmSetWindowAttribute(hwnd, 33, ref preference, sizeof(int));
        }
        catch { }
    }

    // ---------------------------------------------------------------- 占位动作

    // ---------------------------------------------------------------- 更多菜单
    private void ShowMoreMenu()
    {
        if (_current == null) return;
        var panel = new StackPanel { Margin = new Thickness(6) };
        void Item(string text, string iconKey, Action act, Brush fg = null)
        {
            var grid = new Grid { Height = 34 };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(26) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var icon = new Path
            {
                Data = TryFindResource(iconKey) as Geometry,
                Stretch = Stretch.Uniform, Width = 15, Height = 15,
                VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(10, 0, 0, 0),
                Stroke = fg ?? (Brush)(TryFindResource("Muted") ?? Brushes.Gray),
                StrokeThickness = 1.7, Fill = null,
            };
            var label = new TextBlock
            {
                Text = text, FontSize = 10.5, VerticalAlignment = VerticalAlignment.Center,
                Foreground = fg ?? (Brush)(TryFindResource("Text") ?? Brushes.Black),
            };
            Grid.SetColumn(icon, 0);
            Grid.SetColumn(label, 1);
            grid.Children.Add(icon);
            grid.Children.Add(label);
            var btn = new Button
            {
                Content = grid, Background = Brushes.Transparent, BorderThickness = new Thickness(0),
                Cursor = Cursors.Hand, HorizontalContentAlignment = HorizontalAlignment.Stretch,
            };
            btn.Template = RowTemplate();
            btn.Click += (_, _) => { _morePopup.IsOpen = false; act(); };
            panel.Children.Add(btn);
        }

        Item("查看 Token", "Icon.key", OnShowToken);
        Item("重建窗口", "Icon.restart", OnRebuildWindow);
        Item("在文件管理器中显示", "Icon.folder",
            () => DshHost.OpenFolder(System.IO.Path.GetDirectoryName(_current.Entry) ?? ""));
        panel.Children.Add(new Border { Height = 1, Margin = new Thickness(6, 5, 6, 5),
            Background = (Brush)(TryFindResource("InnerBorder") ?? Brushes.Gainsboro) });
        Item("检查更新", "Icon.update", () => CheckUpdateAsync());
        Item("修复实例", "Icon.wrench", () => _ = RepairAsync());
        var danger = (Brush)(TryFindResource("Danger") ?? Brushes.IndianRed);
        Item("卸载实例", "Icon.trash", OnUninstallInstance, danger);

        var card = new Border
        {
            Width = 215, Padding = new Thickness(6), CornerRadius = new CornerRadius(14),
            Background = (Brush)(TryFindResource("CardSolid") ?? Brushes.White),
            BorderBrush = (Brush)(TryFindResource("Border") ?? Brushes.Gainsboro),
            BorderThickness = new Thickness(1), Child = panel,
            Effect = new System.Windows.Media.Effects.DropShadowEffect
            { BlurRadius = 40, ShadowDepth = 16, Direction = 270, Opacity = 0.18, Color = Colors.Black },
        };
        _morePopup = new Popup
        {
            PlacementTarget = MoreBtn, Placement = PlacementMode.Bottom, StaysOpen = false,
            AllowsTransparency = true, VerticalOffset = 6, HorizontalOffset = -160, Child = card,
        };
        _morePopup.IsOpen = true;
    }

    private static ControlTemplate RowTemplate()
    {
        var tmpl = new ControlTemplate(typeof(Button));
        var bd = new FrameworkElementFactory(typeof(Border));
        bd.SetValue(Border.CornerRadiusProperty, new CornerRadius(8));
        bd.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Button.BackgroundProperty));
        var cp = new FrameworkElementFactory(typeof(ContentPresenter));
        cp.SetValue(HorizontalAlignmentProperty, HorizontalAlignment.Stretch);
        bd.AppendChild(cp);
        tmpl.VisualTree = bd;
        return tmpl;
    }

    /// <summary>
    /// 查看 Token：弹一个可选中、可复制的窗口，并把内容写进实例日志。
    /// token 只认日志里**最后一次启动**那一行，并且当场发一次真实请求校验，
    /// 避免给出「上一次运行留下的旧 token」（那是打不开的头号原因）。
    /// </summary>
    /// <summary>拼出「查看 Token」的正文（地址 / token / cookie / 校验结果）。</summary>
    private string BuildTokenText(DshInstance inst)
    {
        var baseUrl = "http://127.0.0.1:" + inst.Port + "/";
        var token = DshHost.FindStartupToken(inst);
        var probe = token == null ? "（日志里没有启动行，实例可能不是管理器启动的）"
            : DshHost.ProbeTokenUrl(baseUrl + "?token=" + token);
        var cookie = AuthCookie.Mint(inst.Port, inst.Home);

        var sb = new System.Text.StringBuilder();
        sb.AppendLine("实例：" + inst.Label);
        sb.AppendLine("端口：" + inst.Port + "（PID " + (inst.Pid > 0 ? inst.Pid.ToString() : "—") + "）");
        sb.AppendLine("数据目录：" + inst.Home);
        sb.AppendLine();
        sb.AppendLine("访问地址（无 token 会 401，这是正常的）：");
        sb.AppendLine(baseUrl);
        if (!string.IsNullOrEmpty(token))
        {
            sb.AppendLine();
            sb.AppendLine("本次启动的 token：");
            sb.AppendLine(token);
            sb.AppendLine();
            sb.AppendLine("带 token 的地址（复制这条）：");
            sb.AppendLine(baseUrl + "?token=" + token);
            sb.AppendLine();
            sb.AppendLine("校验结果：" + probe);
        }
        else sb.AppendLine("校验结果：" + probe);
        sb.AppendLine();
        sb.AppendLine(cookie == null
            ? "认证 cookie：无法签发（实例没有可用的 credentials）"
            : "认证 cookie：" + cookie.Value.Name + " = " + cookie.Value.Value);
        sb.AppendLine();
        sb.AppendLine("提示：如果浏览器里还留着旧的 dsh-auth cookie，会顶掉 token 登录，");
        sb.AppendLine("      用「无痕窗口」打开这条地址即可（或者清掉该站点 cookie）。");
        return sb.ToString();
    }

    /// <summary>查看 Token：打开主题窗口，并允许在窗口里「重新获取 token」。</summary>
    private void OnShowToken()
    {
        if (_current == null) { Toast("先选一个实例"); return; }
        var inst = _current;
        var text = BuildTokenText(inst);
        DshHost.AppendNote(inst, text);
        RefreshLogs(inst);
        ShowTextWindow("查看 Token · " + inst.Label, text, () =>
        {
            var fresh = BuildTokenText(inst);
            DshHost.AppendNote(inst, fresh);
            RefreshLogs(inst);
            return fresh;
        });
    }

    /// <summary>「窗口功能」：列出内置会话窗口的增强能力，并提供可开关项。</summary>
    private void OnWindowFeatures(object sender, RoutedEventArgs e)
    {
        var win = new FeaturesWindow { Owner = this };
        win.Show();
    }

    /// <summary>打开「查看 Token」窗口（外观与主题跟随主窗口）。</summary>
    private void ShowTextWindow(string title, string text, Func<string> refresher = null, bool tokenActions = true)
    {
        var win = new TokenWindow(title, text, refresher, tokenActions) { Owner = this };
        win.Show();
    }

    /// <summary>刷新实例列表（扫一遍本机 + 重新探测运行状态）。</summary>
    private DispatcherTimer _refreshSpin;
    private double _refreshAngle;
    private bool _refreshDone;

    /// <summary>刷新按钮的转圈：像真的等待指示一样转，扫描结束后补齐整圈再停。</summary>
    private void StartRefreshSpin()
    {
        _refreshDone = false;
        _refreshAngle = 0;
        if (_refreshSpin == null)
        {
            _refreshSpin = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(16) };
            _refreshSpin.Tick += (_, _) =>
            {
                var prev = _refreshAngle;
                _refreshAngle = (_refreshAngle + 11) % 360;   // 约 0.52 秒一圈
                if (_refreshAngle < prev) _spinTurns++;       // 过 0 点 = 转完一圈
                if (RefreshRotate != null) RefreshRotate.Angle = _refreshAngle;
                // 扫描完成且已经转过一整圈 → 停在一个完整的圈上
                if (_refreshDone && _spinTurns >= 1)
                {
                    _refreshSpin.Stop();
                    if (RefreshRotate != null) RefreshRotate.Angle = 0;
                    _spinTurns = 0;
                }
            };
        }
        _spinTurns = 0;
        if (!_refreshSpin.IsEnabled) _refreshSpin.Start();
    }

    private int _spinTurns;

    private void StopRefreshSpinWhenDone() => _refreshDone = true;

    /// <summary>刷新实例列表：按钮转圈 + 状态行提示，扫描在后台线程跑。</summary>
    private async void OnRefreshInstances(object sender, RoutedEventArgs e)
    {
        if (RefreshInstances != null) RefreshInstances.IsEnabled = false;
        StartRefreshSpin();
        Toast("实例列表正在刷新中…");
        var sw = System.Diagnostics.Stopwatch.StartNew();
        try
        {
            DshDiscovery.InvalidateListeners();
            var list = await System.Threading.Tasks.Task.Run(() => ScanInstances());
            ApplyInstances(list);
            Diag("refresh scan " + sw.ElapsedMilliseconds + " ms, " + list.Count + " 个实例");
            Toast("实例列表已刷新（" + list.Count + " 个）");
        }
        catch (Exception ex)
        {
            Diag("refresh failed: " + ex);
            Toast("刷新失败：" + ex.Message);
        }
        finally
        {
            if (RefreshInstances != null) RefreshInstances.IsEnabled = true;
            // 扫描结束：告诉定时器可以停，但它会等转满一整圈再停（保证至少转一圈）
            StopRefreshSpinWhenDone();
        }
    }


    /// <summary>重建窗口 = 重启服务 + 重新打开内置会话窗口。</summary>
    private void OnRebuildWindow()
    {
        if (_current == null) return;
        DshHost.Stop(_current, out _);
        var (ok, startMsg) = DshHost.Start(_current, out var msg) ? (true, msg) : (false, msg);
        PollCurrent();
        DshHost.OpenWindow(_current, out var openMsg);
        Toast(ok ? "窗口已重建（" + openMsg + "）" : startMsg);
    }

    /// <summary>
    /// 检查更新：**先把窗口打开**，列表由窗口自己异步拉（顶部转圈），
    /// 用户在窗口里点「检查更新」也能重拉；选好版本点「应用」才真正动手。
    /// </summary>
    private void CheckUpdateAsync()
    {
        if (_current == null) { Toast("先选一个实例"); return; }
        try
        {
            var inst = _current;
            var win = new UpdateWindow(inst) { Owner = this };
            if (win.ShowDialog() != true) { Toast("已取消"); return; }

            _ = ApplySelectedVersionsAsync(inst, win.SelectedDsh, win.SelectedNode);
        }
        catch (Exception ex)
        {
            Diag("check-update failed: " + ex);
            Toast("检查更新失败：" + ex.Message);
        }
    }

    private async System.Threading.Tasks.Task ApplySelectedVersionsAsync(
        DshInstance inst, string dshVersion, string nodeVersion)
    {
        try
        {
            if (!InstanceActions.IsManaged(inst))
            {
                Toast("系统安装（" + inst.Source + "）不受管理器改动");
                return;
            }
            if (!string.IsNullOrWhiteSpace(nodeVersion))
            {
                Toast("正在切换便携 Node 到 " + nodeVersion + "…");
                var (nok, nmsg) = await VersionCatalog.InstallPortableNodeAsync(inst.Dir, nodeVersion, l => Diag(l));
                Toast((nok ? "✔ " : "✘ ") + nmsg);
                if (!nok) return;
            }
            if (!string.IsNullOrWhiteSpace(dshVersion))
            {
                Toast("正在切换到 dsh " + dshVersion + "…");
                var (ok, msg) = await InstanceActions.UpdateAsync(inst, l => Diag(l), dshVersion);
                ReloadInstances();
                if (Quick3Sub != null && ok) Quick3Sub.Text = "当前版本 dsh " + dshVersion;
                Toast((ok ? "✔ " : "✘ ") + msg);
            }
            else if (!string.IsNullOrWhiteSpace(nodeVersion))
                Toast("Node 已切换；重启服务后生效");
            else Toast("未选择要变更的版本");
        }
        catch (Exception ex)
        {
            Diag("apply versions failed: " + ex);
            Toast("应用失败：" + ex.Message);
        }
    }

    private async System.Threading.Tasks.Task RepairAsync()
    {
        if (_current == null) return;
        Toast("正在自检…");
        var (ok, msg) = await InstanceActions.RepairAsync(_current, l => Diag(l));
        Toast((ok ? "✔ " : "✘ ") + msg);
    }

    private void OnUninstallInstance()
    {
        if (_current == null) return;
        var managed = InstanceActions.IsManaged(_current);
        var text = managed
            ? "卸载实例「" + _current.Label + "」？\n\n目录：" + _current.Dir
              + "\n\n确定会停止服务、删除该目录并移除登记。"
            : "「" + _current.Label + "」是系统安装（" + _current.Source + "），管理器不会删除它。\n\n"
              + "需要清理请在文件管理器中操作。现在打开它的目录？";
        var result = MessageBox.Show(this, text, managed ? "卸载实例" : "无法卸载",
            managed ? MessageBoxButton.OKCancel : MessageBoxButton.OK,
            managed ? MessageBoxImage.Warning : MessageBoxImage.Information);
        if (!managed)
        {
            if (result == MessageBoxResult.OK)
                DshHost.OpenFolder(System.IO.Path.GetDirectoryName(_current.Entry) ?? "");
            return;
        }
        if (result != MessageBoxResult.OK) return;
        var (ok, msg) = InstanceActions.Uninstall(_current, deleteDir: true);
        ReloadInstances();
        Toast(msg);
    }

    private void OnOpenWindow(object sender, RoutedEventArgs e)
    {
        if (_current == null) return;
        // 服务没跑就先拉起来，别让人点开一个空窗口
        if (!_current.Running && !DshHost.Start(_current, out var startMsg))
        {
            Toast(startMsg);
            return;
        }
        DshHost.OpenWindow(_current, out var msg);
        RefreshLogs(_current);
        Toast(msg);
    }

    private void OnMore(object sender, RoutedEventArgs e) => ShowMoreMenu();

    private void OnRestartService(object sender, RoutedEventArgs e)
    {
        if (_current == null) { Toast("先选一个实例"); return; }
        try
        {
            DshHost.Stop(_current, out var stopMsg);
            Diag("restart stop -> " + stopMsg);
            DshHost.Start(_current, out var msg);
            Diag("restart start -> " + msg);
            PollCurrent();
            Toast(msg);
        }
        catch (Exception ex)
        {
            Diag("restart failed: " + ex);
            Toast("重启失败：" + ex.Message);   // 不弹窗，只写状态行
        }
    }

    /// <summary>删除实例：停服务 → 删目录 → 移出登记表（只对管理器创建的实例）。</summary>
    private void OnDeleteInstance(object sender, RoutedEventArgs e)
    {
        if (_current == null) { Toast("先选一个实例"); return; }
        var managed = InstanceActions.IsManaged(_current);
        if (!managed)
        {
            MessageBox.Show(this,
                "「" + _current.Label + "」是系统安装（" + _current.Source + "），管理器不会删除它。\n\n" +
                "需要清理请在文件管理器中手动操作：" + _current.Dir,
                "无法删除", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        var ask = MessageBox.Show(this,
            "删除实例「" + _current.Label + "」？\n\n目录：" + _current.Dir +
            "\n\n会先停止服务，然后删除整个目录并从登记表移除，不可恢复。",
            "删除实例", MessageBoxButton.OKCancel, MessageBoxImage.Warning);
        if (ask != MessageBoxResult.OK) return;
        if (_current.Running) DshHost.Stop(_current, out _);
        var (ok, msg) = InstanceActions.Uninstall(_current, deleteDir: true);
        ReloadInstances();
        Toast((ok ? "✔ " : "✘ ") + msg);
        if (!ok) MessageBox.Show(this, msg, "删除实例", MessageBoxButton.OK, MessageBoxImage.Warning);
    }

    private void OnStopService(object sender, RoutedEventArgs e)
    {
        if (_current == null) { Toast("先选一个实例"); return; }
        try
        {
            if (!_current.Running)
            {
                // 未运行 → 这颗按钮是「启动」
                DshHost.Start(_current, out var startMsg);
                Diag("start -> " + startMsg);
                PollCurrent();
                Toast(startMsg);
                return;
            }
            DshHost.Stop(_current, out var msg);
            Diag("stop -> " + msg);
            PollCurrent();
            Toast(msg);
        }
        catch (Exception ex)
        {
            Diag("stop/start failed: " + ex);
            Toast("操作失败：" + ex.Message);   // 不弹窗，只写状态行
        }
    }

    /// <summary>启动/停止服务（左侧快捷控制里的「重启/停止」之外，列表双击也能起停）。</summary>
    private void StartCurrent()
    {
        if (_current == null) return;
        DshHost.Start(_current, out var msg);
        PollCurrent();
        Toast(msg);
    }


    // ---------------------------------------------------------------- 设置页
    private bool _settingsPage;

    /// <summary>给 --shot 用：直接打开设置页。</summary>
    public void OpenSettingsPage() => ShowPage("settings");
    public void OpenTtsPage() => ShowPage("tts");

    private void OnShowOverview(object sender, RoutedEventArgs e) => ShowPage("overview");
    private void OnShowSettings(object sender, RoutedEventArgs e) => ShowPage("settings");
    private void OnShowTts(object sender, RoutedEventArgs e) => ShowPage("tts");

    private void ShowPage(string page)
    {
        var isSettings = page == "settings";
        var isTts = page == "tts";
        _settingsPage = isSettings;
        if (ContentScroll != null) ContentScroll.Visibility = (!isSettings && !isTts) ? Visibility.Visible : Visibility.Collapsed;
        if (SettingsScroll != null) SettingsScroll.Visibility = isSettings ? Visibility.Visible : Visibility.Collapsed;
        if (FeaturesScroll != null) FeaturesScroll.Visibility = isTts ? Visibility.Visible : Visibility.Collapsed;
        if (Breadcrumb != null)
            Breadcrumb.Text = isSettings ? "管理器设置" : (isTts ? "管理器功能" : "实例概览");

        // 侧栏高亮：三选一
        void Style(Button b, bool active)
        {
            if (b == null) return;
            b.Foreground = (Brush)FindResource(active ? "Accent" : "Muted");
            b.Background = active ? (Brush)FindResource("Hover") : Brushes.Transparent;
        }
        Style(OverviewNav, page == "overview");
        Style(SettingsNav, isSettings);
        Style(FeaturesNav, isTts);

        if (isSettings) { FillSettingsInfo(); RefreshSettingsAppearance(); }
        if (isTts) UpdateTtsCard();
    }

    /// <summary>设置页左侧的「管理器信息」列表（键值成对，样式照设计稿的 info-list）。</summary>
    private void FillSettingsInfo()
    {
        if (InfoList == null) return;
        InfoList.Children.Clear();
        var rows = new (string Key, string Value)[]
        {
            ("管理器版本", "v" + AppVersion),
            ("程序目录", AppContext.BaseDirectory.TrimEnd('\\')),
            ("配置目录", System.IO.Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "dsh-manager")),
            ("运行环境", ".NET " + Environment.Version + " · WPF"),
            ("DSH_HOME", DshDiscovery.HomeDir),
            ("实例根目录", _instances.Count > 0 ? _instances[0].Dir : InstanceRegistry.DefaultRoot),
        };
        foreach (var (key, value) in rows)
        {
            var grid = new Grid { MinHeight = 40, Margin = new Thickness(0, 0, 0, 0) };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var k = new TextBlock
            {
                Text = key, FontSize = 10, VerticalAlignment = VerticalAlignment.Center,
                Foreground = (Brush)FindResource("Muted"),
            };
            var v = new TextBlock
            {
                Text = value, FontSize = 9, VerticalAlignment = VerticalAlignment.Center,
                HorizontalAlignment = HorizontalAlignment.Right, TextTrimming = TextTrimming.CharacterEllipsis,
                FontFamily = (FontFamily)FindResource("MonoFont"),
                Foreground = (Brush)FindResource("Text"), MaxWidth = 420,
            };
            var line = new Border
            {
                BorderBrush = (Brush)FindResource("InnerBorder"),
                BorderThickness = new Thickness(0, 0, 0, 1),
                Padding = new Thickness(0, 0, 0, 0),
                Child = grid,
            };
            Grid.SetColumn(k, 0);
            Grid.SetColumn(v, 1);
            grid.Children.Add(k);
            grid.Children.Add(v);
            InfoList.Children.Add(line);
        }
    }

    private void RefreshSettingsAppearance()
    {
        if (SettingsThemeName == null) return;
        SettingsThemeName.Text = ThemeService.Label;
        SettingsModeName.Text = ThemeService.Mode == "night" ? "夜间模式" : "日间模式";
        if (LogLinesBox != null && string.IsNullOrWhiteSpace(LogLinesBox.Text)) LogLinesBox.Text = "800";
    }

    private void OnSettingsChangeTheme(object sender, RoutedEventArgs e)
    {
        ShowPage("overview");             // 主题菜单挂在顶栏的按钮上，先回到仪表盘再弹
        OnThemeTrigger(ThemeTrigger, new RoutedEventArgs());
    }

    private void OnSaveSettings(object sender, RoutedEventArgs e)
    {
        if (int.TryParse(LogLinesBox.Text, out var lines))
        {
            lines = Math.Clamp(lines, 100, 5000);
            LogLinesBox.Text = lines.ToString();
            AppSettings.LogLines = lines;
            AppSettings.Save();
            if (_current != null) RefreshLogs(_current);
            Toast("设置已保存（日志保留 " + lines + " 行）");
        }
        else
        {
            LogLinesBox.Text = AppSettings.LogLines.ToString();
            Toast("日志行数要是数字（100–5000）");
        }
    }

    private void OnOpenManagerLog(object sender, RoutedEventArgs e)
    {
        var dir = System.IO.Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "dsh-manager");
        System.IO.Directory.CreateDirectory(dir);
        DshHost.OpenFolder(dir);
        Toast("已打开管理器数据目录");
    }

    private void OnCopyDiagnostics(object sender, RoutedEventArgs e)
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("=== DSH 管理器诊断 ===");
        sb.AppendLine("版本: " + typeof(MainWindow).Assembly.GetName().Version);
        sb.AppendLine("系统: " + Environment.OSVersion + " / .NET " + Environment.Version);
        sb.AppendLine("DSH_HOME: " + DshDiscovery.HomeDir);
        foreach (var inst in _instances)
            sb.AppendLine($"实例: {inst.Label} | {inst.Source} | dsh {inst.DshVersion} | node {inst.NodeVersion}"
                          + $" | 端口 {inst.Port} | {(inst.Running ? "运行中 PID " + inst.Pid : "已停止")}");
        try
        {
            System.Windows.Clipboard.SetText(sb.ToString());
            Toast("诊断信息已复制到剪贴板");
        }
        catch { Toast("复制失败（剪贴板被占用）"); }
    }

    private void OnCheckUpdate(object sender, RoutedEventArgs e)
    {
        Toast("检查更新：当前是开发版，后续接发布源");
    }


    // ---------------------------------------------------------------- 快捷动作 / 帮助 / 关于
    // ---------------------------------------------------------------- 本地语音（Qwen3-TTS）

    private System.Windows.Threading.DispatcherTimer _ttsTimer;

    private void StartTtsWatcher()
    {
        _ttsTimer = new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromSeconds(3) };
        _ttsTimer.Tick += (_, _) => UpdateTtsCard();
        _ttsTimer.Start();
        UpdateTtsCard();
    }

    private void UpdateTtsCard()
    {
        try
        {
            if (TtsStateText == null) return;
            var running = TtsService.Running;
            var dash = TtsService.DashboardRunning;
            var models = TtsService.ModelsReady;
            var bins = TtsService.BinariesReady;

            TtsStateText.Text = running ? "运行中" : "已停止";
            TtsStateBadge.Background = running
                ? (Brush)FindResource("AccentSoft")
                : (Brush)FindResource("InnerBorder");
            TtsStateText.Foreground = running
                ? (Brush)FindResource("Accent")
                : (Brush)FindResource("Muted");

            TtsPortText.Text = TtsService.Port.ToString();
            TtsModelText.Text = System.IO.Path.GetFileName(TtsService.BackbonePath) + " + " +
                                System.IO.Path.GetFileName(TtsService.CodecPath);
            TtsSizeText.Text = bins
                ? (TtsService.ModelsBytes / 1024 / 1024) + " MB"
                : "—";

            if (!bins) TtsDetail.Text = "缺少 tts-server.exe（services\\tts\\run），需要先放到该目录";
            else if (!models) TtsDetail.Text = "模型未就绪：services\\tts\\models 需要两个 GGUF";
            else if (running) TtsDetail.Text = "管理页 " + (dash ? "已打开" : "未打开") + " · 可直接用于会话朗读";
            else TtsDetail.Text = "已就绪，点「启动服务」拉起";

            TtsStartBtn2.IsEnabled = !running && bins && models;
            TtsStopBtn2.IsEnabled = running;

            if (running && !_ttsVoicesBusy) _ = RefreshTtsVoicesAsync();
        }
        catch { }
    }

    private void OnTtsStart(object sender, RoutedEventArgs e)
    {
        var (ok, msg) = TtsService.Start();
        Toast(msg);
        if (!ok) return;
        System.Threading.Tasks.Task.Delay(1500).ContinueWith(_ => Dispatcher.BeginInvoke(new Action(UpdateTtsCard)));
    }

    private void OnTtsStop(object sender, RoutedEventArgs e)
    {
        var (ok, msg) = TtsService.Stop();
        Toast(msg);
        if (!ok) return;
        System.Threading.Tasks.Task.Delay(800).ContinueWith(_ => Dispatcher.BeginInvoke(new Action(UpdateTtsCard)));
    }

    // ---------------------------------------------------------------- 本地语音：音色 / 试听
    private bool _ttsVoicesBusy;
    private string _ttsPickedFile = "";
    private System.Windows.Media.MediaPlayer _ttsPlayer;

    private async System.Threading.Tasks.Task RefreshTtsVoicesAsync()
    {
        if (TtsVoiceList == null) return;
        _ttsVoicesBusy = true;
        try
        {
            var (ok, err, voices) = await TtsService.ListVoicesAsync();
            TtsVoiceList.Children.Clear();
            TtsVoiceCombo.Items.Clear();
            if (!ok)
            {
                TtsVoiceList.Children.Add(new TextBlock
                {
                    Text = err, FontSize = 8.5,
                    Foreground = (Brush)FindResource("Subtle"),
                });
                return;
            }
            if (voices.Count == 0)
            {
                TtsVoiceList.Children.Add(new TextBlock
                {
                    Text = "还没有音色", FontSize = 8.5,
                    Foreground = (Brush)FindResource("Subtle"),
                });
                return;
            }
            foreach (var v in voices)
            {
                var row = new Grid { Margin = new Thickness(0, 3, 0, 3) };
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

                var name = new TextBlock
                {
                    Text = v.Name, FontSize = 10, Width = 120,
                    VerticalAlignment = VerticalAlignment.Center,
                    Foreground = (Brush)FindResource("Text"),
                };
                var id = new TextBlock
                {
                    Text = v.Id, FontSize = 8.5,
                    VerticalAlignment = VerticalAlignment.Center,
                    Foreground = (Brush)FindResource("Subtle"),
                };
                var rename = new Button
                {
                    Content = "改名", Style = (Style)FindResource("BtnCompact"),
                    Height = 26, Padding = new Thickness(10, 0, 10, 0), FontSize = 9,
                    Margin = new Thickness(0, 0, 8, 0),
                };
                var voiceName = v.Name;
                var voiceId = v.Id;
                rename.Click += async (_, _) =>
                {
                    var next = PromptText("音色改名", "新的音色名字（朗读设置里直接填这个名字）", voiceName);
                    if (string.IsNullOrWhiteSpace(next) || next.Trim() == voiceName) return;
                    var (rok, rmsg) = await TtsService.RenameVoiceAsync(voiceId, next.Trim());
                    Toast(rok ? ("已改名为 " + next.Trim()) : rmsg);
                    if (rok) await RefreshTtsVoicesAsync();
                };
                var del = new Button
                {
                    Content = "删除", Style = (Style)FindResource("BtnCompact"),
                    Height = 26, Padding = new Thickness(10, 0, 10, 0), FontSize = 9,
                };
                del.Click += async (_, _) =>
                {
                    var (dok, dmsg) = await TtsService.DeleteVoiceAsync(voiceId);
                    Toast(dmsg);
                    if (dok) await RefreshTtsVoicesAsync();
                };
                Grid.SetColumn(name, 0);
                Grid.SetColumn(id, 1);
                var actions = new StackPanel { Orientation = Orientation.Horizontal };
                actions.Children.Add(rename);
                actions.Children.Add(del);
                Grid.SetColumn(actions, 2);
                row.Children.Add(name);
                row.Children.Add(id);
                row.Children.Add(actions);
                TtsVoiceList.Children.Add(row);
                TtsVoiceCombo.Items.Add(v.Name);
            }
            if (TtsVoiceCombo.SelectedIndex < 0 && TtsVoiceCombo.Items.Count > 0)
                TtsVoiceCombo.SelectedIndex = 0;
        }
        catch { }
        finally { _ttsVoicesBusy = false; }
    }

    private void OnTtsPickFile(object sender, RoutedEventArgs e)
    {
        var dlg = new Microsoft.Win32.OpenFileDialog
        {
            Title = "选择参考音频（wav，5–20 秒为宜）",
            Filter = "WAV 音频 (*.wav)|*.wav|所有文件 (*.*)|*.*",
        };
        if (dlg.ShowDialog() == true)
        {
            _ttsPickedFile = dlg.FileName;
            if (TtsVoiceNameHint != null) TtsVoiceNameHint.Visibility = Visibility.Collapsed;
            if (TtsVoiceFile != null) TtsVoiceFile.Text = System.IO.Path.GetFileName(dlg.FileName);
            if (TtsVoiceName != null && string.IsNullOrWhiteSpace(TtsVoiceName.Text))
                TtsVoiceName.Text = System.IO.Path.GetFileNameWithoutExtension(dlg.FileName);
        }
    }

    private void OnTtsToggleNewVoice(object sender, RoutedEventArgs e)
    {
        if (TtsNewVoicePanel == null) return;
        var show = TtsNewVoicePanel.Visibility != Visibility.Visible;
        TtsNewVoicePanel.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        if (TtsNewVoiceToggle != null) TtsNewVoiceToggle.Content = show ? "收起" : "新建音色";
    }

    /// <summary>极简输入对话框（改名用）。</summary>
    private string PromptText(string title, string label, string initial)
    {
        var win = new Window
        {
            Title = title, Width = 380, SizeToContent = SizeToContent.Height,
            WindowStartupLocation = WindowStartupLocation.CenterOwner, Owner = this,
            ResizeMode = ResizeMode.NoResize, WindowStyle = WindowStyle.ToolWindow,
            Background = (Brush)FindResource("WindowBackground"),
        };
        var root = new StackPanel { Margin = new Thickness(18) };
        root.Children.Add(new TextBlock
        {
            Text = label, FontSize = 10, Margin = new Thickness(0, 0, 0, 8),
            Foreground = (Brush)FindResource("Muted"),
        });
        var box = new TextBox { Text = initial, FontSize = 12, Height = 32, Padding = new Thickness(8, 0, 8, 0), VerticalContentAlignment = VerticalAlignment.Center };
        root.Children.Add(box);
        var row = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 14, 0, 0) };
        var ok = new Button { Content = "确定", Style = (Style)FindResource("BtnPrimary"), Height = 30, Padding = new Thickness(16, 0, 16, 0), IsDefault = true };
        var cancel = new Button { Content = "取消", Style = (Style)FindResource("BtnCompact"), Height = 30, Padding = new Thickness(14, 0, 14, 0), Margin = new Thickness(8, 0, 0, 0), IsCancel = true };
        ok.Click += (_, _) => { win.DialogResult = true; };
        row.Children.Add(ok);
        row.Children.Add(cancel);
        root.Children.Add(row);
        win.Content = root;
        box.Focus();
        box.SelectAll();
        return win.ShowDialog() == true ? box.Text : null;
    }

    private void OnTtsVoiceNameChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        if (TtsVoiceNameHint == null) return;
        TtsVoiceNameHint.Visibility = string.IsNullOrEmpty(TtsVoiceName.Text)
            ? Visibility.Visible : Visibility.Collapsed;
    }

    private async void OnTtsUpload(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_ttsPickedFile) || !System.IO.File.Exists(_ttsPickedFile))
        {
            Toast("先选一段参考音频");
            return;
        }
        var name = (TtsVoiceName?.Text ?? "").Trim();
        if (name.Length == 0) { Toast("给音色起个名字"); return; }
        Toast("上传中…（要重新编码参考音频）");
        var (ok, msg) = await TtsService.CreateVoiceAsync(name, _ttsPickedFile);
        Toast(msg);
        if (ok)
        {
            _ttsPickedFile = "";
            if (TtsVoiceFile != null) TtsVoiceFile.Text = "未选择文件";
            if (TtsVoiceName != null) TtsVoiceName.Text = "";
            await RefreshTtsVoicesAsync();
        }
    }

    private async void OnTtsSynth(object sender, RoutedEventArgs e)
    {
        var text = (TtsSynthText?.Text ?? "").Trim();
        if (text.Length == 0) { Toast("先输入要合成的文字"); return; }
        var voice = (TtsVoiceCombo?.SelectedItem as string) ?? "";
        if (TtsSynthStatus != null) TtsSynthStatus.Text = "合成中…（CPU 约 0.3 倍速）";
        var sw = System.Diagnostics.Stopwatch.StartNew();
        var (ok, err, wav, secs, elapsed) = await TtsService.SynthesizeAsync(text, voice);
        sw.Stop();
        if (!ok)
        {
            if (TtsSynthStatus != null) TtsSynthStatus.Text = "失败：" + err;
            return;
        }
        if (TtsSynthStatus != null)
            TtsSynthStatus.Text = $"完成：音频 {secs:F1}s · 用时 {elapsed.TotalSeconds:F1}s";
        try
        {
            _ttsPlayer ??= new System.Windows.Media.MediaPlayer();
            _ttsPlayer.Open(new Uri(wav));
            _ttsPlayer.Play();
        }
        catch (Exception ex) { Toast("播放失败：" + ex.Message); }
    }

    private void OnTtsFolder(object sender, RoutedEventArgs e)
    {
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = TtsService.Root,
                UseShellExecute = true,
            });
        }
        catch (Exception ex) { Toast("打开目录失败：" + ex.Message); }
    }

    private void OnTtsLog(object sender, RoutedEventArgs e)
    {
        var log = System.IO.Path.Combine(TtsService.LogDir, "server.log");
        try
        {
            if (!System.IO.File.Exists(log)) { Toast("还没有日志：" + log); return; }
            var text = System.IO.File.ReadAllText(log);
            if (text.Length > 20000) text = text.Substring(text.Length - 20000);
            ShowTextWindow("本地语音日志", text, null);
        }
        catch (Exception ex) { Toast("读取日志失败：" + ex.Message); }
    }

    private void OnTtsOpen(object sender, RoutedEventArgs e)
    {
        var (ok, url) = TtsService.EnsureDashboard();
        if (!ok) { Toast(url); return; }
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(url) { UseShellExecute = true }); }
        catch (Exception ex) { Toast("打开管理页失败：" + ex.Message); }
        Toast("管理页：" + url);
    }

    private void OnQuickToken(object sender, MouseButtonEventArgs e) => OnShowToken();
    private void OnQuickUpdate(object sender, MouseButtonEventArgs e) => CheckUpdateAsync();
    private void OnQuickFolder(object sender, MouseButtonEventArgs e)
    {
        if (_current == null) return;
        DshHost.OpenFolder(System.IO.Path.GetDirectoryName(_current.Entry) ?? DshDiscovery.HomeDir);
        Toast("已打开实例目录");
    }

    // 子窗口都做成非模态：开着「管理插件」时管理器本身和 DSH 会话窗口都还能用
    private HelpWindow _helpWin;
    private NewInstanceWindow _newInstanceWin;
    private PluginWindow _pluginWin;

    private void OnHelp(object sender, RoutedEventArgs e)
    {
        if (_helpWin != null) { _helpWin.Activate(); return; }
        var win = new HelpWindow { Owner = this };
        _helpWin = win;
        win.Closed += (_, _) => _helpWin = null;
        win.Show();
    }

    private void OnAbout(object sender, RoutedEventArgs e)
    {
        var text = "DeepSeek Harness 管理器\n\n"
                   + "版本 " + typeof(MainWindow).Assembly.GetName().Version + "\n"
                   + ".NET " + Environment.Version + " · WPF + WebView2\n"
                   + "DSH_HOME：" + DshDiscovery.HomeDir + "\n\n"
                   + "Windows 版：管理器与桌面窗口合为一体。\n"
                   + "https://github.com/cuteG41cute/dsh-desktop";
        MessageBox.Show(this, text, "关于", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    private void OnNewInstance(object sender, RoutedEventArgs e)
    {
        if (_newInstanceWin != null) { _newInstanceWin.Activate(); return; }
        var win = new NewInstanceWindow { Owner = this };
        _newInstanceWin = win;
        // 非模态窗口没有 DialogResult：装完由窗口自己发事件，这里刷新列表
        win.Created += dir =>
        {
            ReloadInstances();
            Toast("实例已创建：" + dir);
        };
        win.Closed += (_, _) => _newInstanceWin = null;
        win.Show();
    }

    private void OnManagePlugins(object sender, MouseButtonEventArgs e)
    {
        if (_current == null) { Toast("先选一个实例"); return; }
        if (_pluginWin != null) { _pluginWin.Activate(); return; }
        var win = new PluginWindow(_current) { Owner = this };
        _pluginWin = win;
        win.Closed += (_, _) => _pluginWin = null;
        win.Show();
    }

    private void Toast(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        RuntimeLine.Text = text.Length > 46 ? text.Substring(0, 46) + "…" : text;
    }
}
