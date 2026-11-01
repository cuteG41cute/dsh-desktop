using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json;
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
///   2. 手机端桥 —— 本机跑着 dsh-mobile-bridge（默认 8099）时优先走桥，
///      这样设置里才有「手机端」面板；桥自检不过就退回直连，窗口一定能打开。
/// </summary>
public partial class DshWebWindow : Window
{
    private readonly DshInstance _inst;
    private bool _ready;
    private string _baseUrl;
    private bool _viaBridge;

    /// <summary>同一个端口只开一个窗口（多点几次只是提回前台）。</summary>
    private static readonly Dictionary<int, DshWebWindow> Open = new();

    public DshWebWindow(DshInstance inst)
    {
        InitializeComponent();
        _inst = inst;
        Title = "DeepSeek Harness · " + inst.Label;
        StateChanged += (_, _) => UpdateMaxGlyph();
        Closed += (_, _) =>
        {
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
            core.Settings.AreDevToolsEnabled = true;
            core.Settings.IsStatusBarEnabled = false;

            // 认证：自签一枚 cookie 塞进 WebView2 的 CookieManager（比环境变量更直接）
            var cookie = AuthCookie.Mint(_inst.Port);
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
            await NavigateAsync();
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

    // ---------------------------------------------------------------- 地址 / 桥
    /// <summary>
    /// 决定窗口打开哪个地址：
    ///  - 本机有 dsh-mobile-bridge 且自检通过、并且桥指向的就是这个实例 → 走桥（有「手机端」面板）
    ///  - 否则直连实例端口（桥是可选增强，不能挡住开窗）
    /// 桥的上游端口默认 3080，桥只能在它自己的上游上工作，所以端口对不上就直连。
    /// </summary>
    private static int BridgePort =>
        int.TryParse(Environment.GetEnvironmentVariable("DSH_MANAGER_BRIDGE_PORT"), out var p) && p > 0
            ? p : 8099;

    private async System.Threading.Tasks.Task NavigateAsync()
    {
        ShowStatus("正在连接 DSH…", "端口 " + _inst.Port, retry: false);
        _baseUrl = "http://127.0.0.1:" + _inst.Port + "/";
        _viaBridge = false;

        // 桥的上游固定是 3080（桥自己按 --target / DSH_BRIDGE_TARGET 定，默认 3080），
        // 所以只有 3080 上的实例能通过桥看；别的实例直连，手机侧功能不受影响。
        var direct = Environment.GetEnvironmentVariable("DSH_MANAGER_DIRECT") == "1";
        if (!direct && _inst.Port == 3080 && await ProbeBridgeAsync() == 200)
        {
            _baseUrl = "http://127.0.0.1:" + BridgePort + "/";
            _viaBridge = true;
        }

        UpdateTitleText();
        Diag("navigate " + _baseUrl + " bridge=" + _viaBridge);
        if (_ready) Web.CoreWebView2.Navigate(_baseUrl);
    }

    /// <summary>桥的 /__selftest：会真的向上游取一次首页并跑完注入管线，ok=true 才算桥可用。</summary>
    private static async System.Threading.Tasks.Task<int> ProbeBridgeAsync()
    {
        // 先花 300ms 看端口在不在：桥没跑时别让窗口白等 HTTP 超时
        if (!PortOpen(BridgePort)) return 0;
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(6) };
            using var resp = await http.GetAsync("http://127.0.0.1:" + BridgePort + "/__selftest");
            if (resp.StatusCode != System.Net.HttpStatusCode.OK) return 0;
            var text = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(text);
            if (doc.RootElement.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True) return 200;
            return 0;
        }
        catch
        {
            return 0;
        }
    }

    private static bool PortOpen(int port)
    {
        try
        {
            using var client = new System.Net.Sockets.TcpClient();
            var task = client.ConnectAsync("127.0.0.1", port);
            return task.Wait(300) && client.Connected;
        }
        catch { return false; }
    }

    private void UpdateTitleText()
    {
        var text = _inst.Label + " · 端口 " + _inst.Port + (_viaBridge ? " · 手机端桥" : "");
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
        _ = NavigateAsync();
    }

    // ---------------------------------------------------------------- 工具栏
    private void OnBack(object sender, RoutedEventArgs e)
    {
        if (_ready && Web.CoreWebView2.CanGoBack) Web.CoreWebView2.GoBack();
    }

    private void OnReload(object sender, RoutedEventArgs e)
    {
        if (_ready) Web.CoreWebView2.Reload();
    }

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
