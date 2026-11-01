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
        // 实例在 OnLoaded 里扫描（构造时还没有扫描结果，不能索引）
        Loaded += OnLoaded;
        SizeChanged += (_, _) =>
        {
            UpdateShellClip();
            ApplyResponsive();
        };
        ThemeService.ThemeChanged += OnThemeChanged;
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
        try
        {
            if (TryFindResource("AppRadiusValue") is double d) r = d;
        }
        catch { }
        var w = ShellContent.ActualWidth;
        var h = ShellContent.ActualHeight;
        if (w <= 0 || h <= 0) return;
        ShellContent.Clip = new RectangleGeometry(new Rect(0, 0, w, h), r, r);
        // 整个外壳也裁一次圆角：只靠 Border.CornerRadius 时，里面那层半透明底色
        // 仍会在四角画出方的半透明三角（用户看到的「半透明尖角」）。
        if (Shell != null && Shell.ActualWidth > 0 && Shell.ActualHeight > 0)
            Shell.Clip = new RectangleGeometry(
                new Rect(0, 0, Shell.ActualWidth, Shell.ActualHeight), r, r);
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
            var cols = avail >= 900 ? 4 : (avail >= 620 ? 3 : 2);
            var gap = 11.0;
            var cardW = Math.Max(150, Math.Floor((avail - gap * (cols - 1)) / cols));
            var cards = new[] { Quick1, Quick2, Quick3, Quick4 };
            for (var i = 0; i < cards.Length; i++)
            {
                cards[i].Width = cardW;
                cards[i].Margin = new Thickness(0, 0, (i % cols == cols - 1) ? 0 : gap, gap);
            }
        }
        catch { }
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        ApplyRoundedCorners();
        ReloadInstances();
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
        FooterPath.Text = "实例根目录 · " + RootDir;
        ApplyResponsive();
    }

    private static string RootDir =>
        System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            "Programs");

    // ---------------------------------------------------------------- 主题
    private void OnThemeChanged()
    {
        Dispatcher.BeginInvoke(new Action(RefreshThemeUi));
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
    private void ReloadInstances()
    {
        var scanned = DshDiscovery.Scan().ToList();
        DshDiscovery.AttachRunning(scanned);      // 反查「现在真正在跑的是哪个」
        DshDiscovery.ApplyRegistryPorts(scanned); // 管理器创建的实例用登记过的端口
        _instances = scanned
            .OrderByDescending(i => i.Running)
            .ThenBy(i => i.SortKey)
            .ToList();
        _current = _instances.FirstOrDefault();
        BuildInstanceList();
        if (_current != null)
        {
            ShowInstance(_current);
            RefreshLogs(_current);
        }
        else ShowEmptyState();
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
        StatusBadgeText.Text = "未安装";
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
        var text = DshHost.Tail(inst, AppSettings.LogLines);
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
        StatusBadgeText.Text = inst.Running ? "运行中" : "未运行";
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
        }
        else
        {
            _isMaximized = false;
            Shell.Margin = new Thickness(0);
            Shell.CornerRadius = (CornerRadius)FindResource("AppRadius");
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
            var preference = 1; // DWMWCP_DONOTROUND
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
        Item("检查更新", "Icon.update", () => _ = CheckUpdateAsync());
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

    private void OnShowToken()
    {
        if (_current == null) return;
        var url = "http://127.0.0.1:" + _current.Port + "/";
        try
        {
            Clipboard.SetText(url);
            Toast("访问地址已复制：" + url);
        }
        catch { Toast("复制失败（剪贴板被占用）"); }
    }

    /// <summary>重建窗口 = 重启服务 + 重新拉起桌面版启动器（窗口是它管的，不是浏览器）。</summary>
    private void OnRebuildWindow()
    {
        if (_current == null) return;
        DshHost.Stop(_current, out _);
        var (ok, startMsg) = DshHost.Start(_current, out var msg) ? (true, msg) : (false, msg);
        PollCurrent();
        DshHost.OpenWindow(_current, out var openMsg);
        Toast(ok ? "窗口已重建（" + openMsg + "）" : startMsg);
    }

    private async System.Threading.Tasks.Task CheckUpdateAsync()
    {
        if (_current == null) return;
        Toast("正在检查更新…");
        var (ok, msg) = await InstanceActions.UpdateAsync(_current, l => Diag(l));
        if (ok)
        {
            ReloadInstances();
            Toast(msg);
        }
        else Toast(msg);
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
        if (_current == null) return;
        DshHost.Stop(_current, out _);
        DshHost.Start(_current, out var msg);
        PollCurrent();
        Toast(msg);
    }

    private void OnStopService(object sender, RoutedEventArgs e)
    {
        if (_current == null) return;
        DshHost.Stop(_current, out var msg);
        PollCurrent();
        Toast(msg);
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
    public void OpenSettingsPage() => ShowPage(true);

    private void OnShowOverview(object sender, RoutedEventArgs e) => ShowPage(false);
    private void OnShowSettings(object sender, RoutedEventArgs e) => ShowPage(true);

    private void ShowPage(bool settings)
    {
        _settingsPage = settings;
        if (ContentScroll != null) ContentScroll.Visibility = settings ? Visibility.Collapsed : Visibility.Visible;
        if (SettingsScroll != null) SettingsScroll.Visibility = settings ? Visibility.Visible : Visibility.Collapsed;
        if (Breadcrumb != null) Breadcrumb.Text = settings ? "管理器设置" : "实例概览";
        // 侧栏高亮跟着当前页走
        if (OverviewNav != null && SettingsNav != null)
        {
            OverviewNav.Foreground = (Brush)FindResource(settings ? "Muted" : "Accent");
            OverviewNav.Background = settings ? Brushes.Transparent : (Brush)FindResource("Hover");
            SettingsNav.Foreground = (Brush)FindResource(settings ? "Accent" : "Muted");
            SettingsNav.Background = settings ? (Brush)FindResource("Hover") : Brushes.Transparent;
        }
        if (settings) { FillSettingsInfo(); RefreshSettingsAppearance(); }
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
            ("实例根目录", _instances.Count > 0
                ? System.IO.Path.GetDirectoryName(System.IO.Path.GetDirectoryName(_instances[0].Entry) ?? "")
                : "—"),
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
        ShowPage(false);                 // 主题菜单挂在顶栏的按钮上，先回到仪表盘再弹
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
    private void OnQuickToken(object sender, MouseButtonEventArgs e) => OnShowToken();
    private void OnQuickUpdate(object sender, MouseButtonEventArgs e) => _ = CheckUpdateAsync();
    private void OnQuickFolder(object sender, MouseButtonEventArgs e)
    {
        if (_current == null) return;
        DshHost.OpenFolder(System.IO.Path.GetDirectoryName(_current.Entry) ?? DshDiscovery.HomeDir);
        Toast("已打开实例目录");
    }

    private void OnHelp(object sender, RoutedEventArgs e)
    {
        var win = new HelpWindow { Owner = this };
        win.ShowDialog();
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
        var win = new NewInstanceWindow { Owner = this };
        if (win.ShowDialog() == true)
        {
            ReloadInstances();
            Toast("实例已创建：" + win.CreatedDir);
        }
    }

    private void OnManagePlugins(object sender, MouseButtonEventArgs e)
    {
        if (_current == null) { Toast("先选一个实例"); return; }
        var win = new PluginWindow(_current) { Owner = this };
        win.ShowDialog();
    }

    private void Toast(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        RuntimeLine.Text = text.Length > 46 ? text.Substring(0, 46) + "…" : text;
    }
}
