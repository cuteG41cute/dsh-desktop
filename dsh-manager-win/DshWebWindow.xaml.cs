using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using DshManager.Services;
using Microsoft.Web.WebView2.Core;

namespace DshManager;

/// <summary>
/// DSH 会话窗口：内置 WebView2，和 Linux 版的桌面窗口是同一个角色。
/// 它跟管理器是**同一个工程/同一个包**（不再依赖外部的 DSH Desktop.exe / launcher.ps1）。
///
/// 两件事是从 Linux 启动器（launcher.ps1）搬过来的：
///   1. 认证 cookie —— 自己签发并验证过，服务是外部启动的也能用；
///   2. 直连实例端口 —— 电脑端窗口就走 127.0.0.1:&lt;port&gt;，不经过手机端桥（8099）。
///      桥是给局域网里的手机/平板用的反向代理，桌面窗口再绕它一圈没意义。
/// </summary>
public partial class DshWebWindow : Window
{

    /// <summary>当前打开着的会话窗口（改「窗口功能」开关后统一重载）。</summary>
    public static readonly List<DshWebWindow> Live = new List<DshWebWindow>();

    public static void ReloadAll()
    {
        DshWebWindow[] all;
        lock (Live) all = Live.ToArray();
        foreach (var w in all)
        {
            try { w.ReloadPage(); } catch { }
        }
    }

    private readonly DshInstance _inst;
    private bool _ready;
    private string _baseUrl;
    private string _token;

    /// <summary>同一个端口只开一个窗口（多点几次只是提回前台）。</summary>
    private static readonly Dictionary<int, DshWebWindow> Open = new();

    public DshWebWindow(DshInstance inst)
    {
        InitializeComponent();
        _inst = inst;
        Title = "DeepSeek Harness · " + inst.Label;
        StateChanged += (_, _) => UpdateMaxGlyph();
        lock (Live) Live.Add(this);
        Closed += (_, _) =>
        {
            lock (Live) Live.Remove(this);
            lock (Open) Open.Remove(inst.Port);
            ThemeService.ThemeChanged -= ApplyThemeToWeb;
        };
        Loaded += OnLoaded;

        // WebView2 是原生子窗口，WPF 裁不到它 —— 圆角交给 DWM（Win11）
        FramelessWindow.SetCornerPreference(this, FramelessWindow.Round);
        // 四边缩放自己做（WindowChrome 的 ResizeBorderThickness 在这套窗口上不生效）
        FramelessWindow.EnableResize(this, 8, () => WindowState == WindowState.Maximized);
    }

    public static bool OpenOrFocus(DshInstance inst, out string message)
    {
        message = "";
        lock (Open)
        {
            if (Open.TryGetValue(inst.Port, out var existing))
            {
                if (existing.WindowState == WindowState.Minimized) existing.WindowState = WindowState.Normal;
                existing.Activate();
                existing.Topmost = true;
                existing.Topmost = false;
                message = "窗口已在前台（端口 " + inst.Port + "）";
                return true;
            }
        }
        try
        {
            var win = new DshWebWindow(inst);
            lock (Open) Open[inst.Port] = win;
            win.Show();
            message = "已打开内置窗口（端口 " + inst.Port + "）";
            return true;
        }
        catch (Exception ex)
        {
            message = "打开内置窗口失败：" + ex.Message;
            return false;
        }
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        try
        {
            Diag("loaded");
            // 每个用户独立的数据目录，别和外部桌面版打架
            var dataDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "dsh-manager", "webview2");
            Directory.CreateDirectory(dataDir);
            var env = await CoreWebView2Environment.CreateAsync(null, dataDir);
            await Web.EnsureCoreWebView2Async(env);
            Diag("webview2 ready");

            var core = Web.CoreWebView2;
            Watchdog.Breadcrumb("web window ready: port " + _inst.Port);
            AttachPreviewTools(core);
            ProbePreviewDomOnce(core);
            HookDomDumpHotkey();
            core.Settings.AreDevToolsEnabled = true;
            core.Settings.IsStatusBarEnabled = false;

            // 认证：自签一枚 cookie 塞进 WebView2 的 CookieManager（比环境变量更直接）
            var cookie = AuthCookie.Mint(_inst.Port, _inst.Home);
            Diag("cookie " + (cookie == null ? "none" : "minted " + cookie.Value.Name));
            if (cookie != null)
            {
                var c = core.CookieManager.CreateCookie(cookie.Value.Name, cookie.Value.Value, "127.0.0.1", "/");
                core.CookieManager.AddOrUpdateCookie(c);
            }

            core.NavigationCompleted += (_, args) =>
            {
                Diag("nav " + args.WebErrorStatus + " success=" + args.IsSuccess);
                if (args.IsSuccess)
                {
                    HideStatus();
                }
                else
                {
                    ShowStatus("打不开 DSH 页面",
                        "端口 " + _inst.Port + " · " + args.WebErrorStatus + "\n" +
                        "服务可能还没起来，或者端口被别的东西占了。", retry: true);
                }
                UpdateTitleText();
            };
            core.DocumentTitleChanged += (_, _) =>
            {
                var t = core.DocumentTitle;
                if (string.IsNullOrWhiteSpace(t)) return;
                Title = t.Contains("DeepSeek Harness") ? t : t + " · DeepSeek Harness";
            };
            core.NewWindowRequested += (_, args) =>
            {
                // 页面要开新窗口：用系统浏览器接住（登录等第三方页面）
                try { Process.Start(new ProcessStartInfo(args.Uri) { UseShellExecute = true }); } catch { }
                args.Handled = true;
            };

            _ready = true;
            NavigateToInstance();
            ThemeService.ThemeChanged += ApplyThemeToWeb;
            ApplyThemeToWeb();
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, "内置窗口初始化失败：" + ex.Message + "\n\n（需要 Edge WebView2 运行时）",
                "DeepSeek Harness", MessageBoxButton.OK, MessageBoxImage.Warning);
            Close();
        }
    }

    // ---------------------------------------------------------------- 地址
    /// <summary>
    /// 电脑端窗口**永远直连实例自己的端口**（127.0.0.1:&lt;port&gt;）。
    /// 手机端桥（8099）只服务手机/平板：那是给局域网设备用的反向代理，
    /// 桌面窗口本来就在同一台机器上，绕一圈只会多一跳、还多一个「桥没在跑」的依赖。
    /// </summary>
    private void NavigateToInstance()
    {
        ShowStatus("正在连接 DSH…", "端口 " + _inst.Port, retry: false);
        _baseUrl = "http://127.0.0.1:" + _inst.Port + "/";
        // 源码实例/独立 dsh-home 会打印 http://127.0.0.1:PORT/?token=XXX，
        // cookie 蒙不出来时就带着这个 token 进去（一次性入口，之后自己种 cookie）。
        if (_token == null)
        {
            var m = System.Text.RegularExpressions.Regex.Match(
                DshHost.Tail(_inst, 80), @"127\.0\.0\.1:\d+/\?token=([A-Za-z0-9_\-\.]+)");
            if (m.Success) _token = m.Groups[1].Value;
        }
        if (!string.IsNullOrEmpty(_token)) _baseUrl += "?token=" + _token;
        UpdateTitleText();
        Diag("navigate " + _baseUrl);
        if (_ready) Web.CoreWebView2.Navigate(_baseUrl);
    }

    private void UpdateTitleText()
    {
        var text = _inst.Label + " · 端口 " + _inst.Port;
        if (TitleText != null) TitleText.Text = text;
    }

    // ---------------------------------------------------------------- 主题 / 状态
    /// <summary>
    /// DSH 页面的昼夜由 prefers-color-scheme 决定（设置里选「跟随系统」时），
    /// 管理器的昼夜直接映射过去，窗口里外颜色才一致。
    /// </summary>
    private void ApplyThemeToWeb()
    {
        var night = string.Equals(ThemeService.Mode, "night", StringComparison.OrdinalIgnoreCase);
        try
        {
            Web.DefaultBackgroundColor = SolidColor("CardSolid");
        }
        catch { }
        if (!_ready) return;
        try
        {
            Web.CoreWebView2.Profile.PreferredColorScheme = night
                ? CoreWebView2PreferredColorScheme.Dark
                : CoreWebView2PreferredColorScheme.Light;
        }
        catch { }
    }

    private static System.Drawing.Color SolidColor(string brushKey)
    {
        try
        {
            if (Application.Current.TryFindResource(brushKey) is SolidColorBrush b)
                return System.Drawing.Color.FromArgb(b.Color.A, b.Color.R, b.Color.G, b.Color.B);
        }
        catch { }
        return System.Drawing.Color.FromArgb(255, 255, 255, 255);
    }

    private static void Diag(string text)
    {
        try
        {
            var dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "dsh-manager");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "web.log"),
                DateTime.Now.ToString("HH:mm:ss.fff ") + text + Environment.NewLine);
        }
        catch { }
    }

    private void ShowStatus(string title, string detail, bool retry)
    {
        StatusTitle.Text = title;
        StatusDetail.Text = detail ?? "";
        RetryBtn.Visibility = retry ? Visibility.Visible : Visibility.Collapsed;
        StatusOverlay.Visibility = Visibility.Visible;
    }

    private void HideStatus() => StatusOverlay.Visibility = Visibility.Collapsed;

    private void OnRetry(object sender, RoutedEventArgs e)
    {
        NavigateToInstance();
    }

    // ---------------------------------------------------------------- 工具栏
    private void OnBack(object sender, RoutedEventArgs e)
    {
        if (_ready && Web.CoreWebView2.CanGoBack) Web.CoreWebView2.GoBack();
    }

    /// <summary>页面重载（改「窗口功能」开关后用它让注入脚本重新生效）。</summary>
    public void ReloadPage()
    {
        if (_ready) Web.CoreWebView2.Reload();
    }

    private void OnReload(object sender, RoutedEventArgs e) => ReloadPage();

    private void OnOpenExternal(object sender, RoutedEventArgs e)
    {
        try { Process.Start(new ProcessStartInfo(_baseUrl ?? ("http://127.0.0.1:" + _inst.Port + "/")) { UseShellExecute = true }); }
        catch { }
    }

    private void OnMinimize(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void OnMaximize(object sender, RoutedEventArgs e) => ToggleMaximize();

    private void OnClose(object sender, RoutedEventArgs e) => Close();

    private void ToggleMaximize()
    {
        WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
    }

    private void UpdateMaxGlyph()
    {
        if (MaxGlyph == null) return;
        MaxGlyph.Data = WindowState == WindowState.Maximized
            ? Geometry.Parse("M 6 8 H 22 V 24 H 10 M 8 6 H 24 V 22 H 8")  // 还原
            : Geometry.Parse("M 4 4 H 20 V 20 H 4 Z");
    }

    private void OnDrag(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Left) return;
        for (var d = e.OriginalSource as DependencyObject; d != null; d = VisualTreeHelper.GetParent(d))
            if (d is System.Windows.Controls.Button) return;
        if (e.ClickCount == 2) { ToggleMaximize(); return; }
        try { DragMove(); } catch { }
    }
}
