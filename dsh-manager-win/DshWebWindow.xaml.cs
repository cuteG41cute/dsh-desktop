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
/// 现在它跟管理器是**同一个工程/同一个包**（不再依赖外部的 DSH Desktop.exe）。
/// </summary>
public partial class DshWebWindow : Window
{
    private readonly DshInstance _inst;
    private bool _ready;
    private bool _max;

    /// <summary>同一个端口只开一个窗口（多点几次只是提回前台）。</summary>
    private static readonly Dictionary<int, DshWebWindow> Open = new();

    public DshWebWindow(DshInstance inst)
    {
        InitializeComponent();
        _inst = inst;
        Title = "DeepSeek Harness · " + inst.Label;
        TitleText.Text = inst.Label + " · 端口 " + inst.Port;
        Loaded += OnLoaded;
        Closed += (_, _) => { lock (Open) Open.Remove(inst.Port); };
        ThemeService.ThemeChanged += () => { };
    }

    public static bool OpenOrFocus(DshInstance inst, out string message)
    {
        message = "";
        lock (Open)
        {
            if (Open.TryGetValue(inst.Port, out var existing))
            {
                existing.Activate();
                existing.WindowState = existing.WindowState == WindowState.Minimized
                    ? WindowState.Normal : existing.WindowState;
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
            // 每个用户独立的数据目录，别和外部桌面版打架
            var dataDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "dsh-manager", "webview2");
            Directory.CreateDirectory(dataDir);
            var env = await CoreWebView2Environment.CreateAsync(null, dataDir);
            await Web.EnsureCoreWebView2Async(env);

            var core = Web.CoreWebView2;
            core.Settings.AreDevToolsEnabled = true;
            core.Settings.IsStatusBarEnabled = false;

            // 认证：自签一枚 cookie 塞进 WebView2 的 CookieManager（比环境变量更直接）
            var cookie = AuthCookie.Mint(_inst.Port);
            if (cookie != null)
            {
                var c = core.CookieManager.CreateCookie(cookie.Value.Name, cookie.Value.Value, "127.0.0.1", "/");
                core.CookieManager.AddOrUpdateCookie(c);
            }

            core.NavigationCompleted += (_, args) =>
            {
                TitleText.Text = (_inst.Label + " · 端口 " + _inst.Port
                                  + (args.IsSuccess ? "" : " · 加载失败 " + args.WebErrorStatus));
            };
            core.DocumentTitleChanged += (_, _) =>
            {
                var t = core.DocumentTitle;
                if (!string.IsNullOrWhiteSpace(t)) Title = t + " · DeepSeek Harness";
            };
            core.NewWindowRequested += (_, args) =>
            {
                // 页面要开新窗口：用系统浏览器接住（登录等第三方页面）
                try { Process.Start(new ProcessStartInfo(args.Uri) { UseShellExecute = true }); } catch { }
                args.Handled = true;
            };

            _ready = true;
            Web.Source = new Uri("http://127.0.0.1:" + _inst.Port + "/");
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, "内置窗口初始化失败：" + ex.Message + "\n\n（需要 Edge WebView2 运行时）",
                "DeepSeek Harness", MessageBoxButton.OK, MessageBoxImage.Warning);
            Close();
        }
    }

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
        try { Process.Start(new ProcessStartInfo("http://127.0.0.1:" + _inst.Port + "/") { UseShellExecute = true }); }
        catch { }
    }

    private void OnMinimize(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void OnMaximize(object sender, RoutedEventArgs e)
    {
        _max = !_max;
        Shell.Margin = new Thickness(_max ? 0 : 0);
        WindowState = _max ? WindowState.Maximized : WindowState.Normal;
    }

    private void OnClose(object sender, RoutedEventArgs e) => Close();

    private void OnDrag(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Left) return;
        for (var d = e.OriginalSource as DependencyObject; d != null; d = VisualTreeHelper.GetParent(d))
            if (d is System.Windows.Controls.Button) return;
        if (e.ClickCount == 2) { OnMaximize(sender, e); return; }
        try { DragMove(); } catch { }
    }
}
