using System;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Threading.Tasks;
using System.Windows.Threading;
using DshManager.Services;

namespace DshManager;

public partial class App : Application
{
    private static System.Threading.Mutex _single;
    private static System.Windows.Forms.NotifyIcon _tray;
    private bool _quitting;

    /// <summary>真正退出（托盘菜单走这里），否则关窗口只是收进托盘。</summary>
    public void QuitForReal()
    {
        _quitting = true;
        _tray?.Dispose();
        _tray = null;
        Shutdown();
    }

    public bool Quitting => _quitting;

    private static string LogDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "dsh-manager");

    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += (_, ex) =>
        {
            Log("unhandled: " + ex.Exception);
            ex.Handled = true;
            MessageBox.Show(ex.Exception.Message, "DeepSeek Harness 管理器");
        };
        AppDomain.CurrentDomain.UnhandledException += (_, ex) => Log("domain: " + ex.ExceptionObject);
        try
        {
            // ---- 单实例：已经有管理器在跑就把它提到前台，然后退出本次 ----
            _single = new System.Threading.Mutex(true, "Global\\DshManager", out var isNew);
            if (!isNew)
            {
                var other = System.Diagnostics.Process.GetProcessesByName("DshManager")
                    .FirstOrDefault(p => p.Id != System.Diagnostics.Process.GetCurrentProcess().Id);
                if (other != null && other.MainWindowHandle != IntPtr.Zero)
                {
                    SetForegroundWindow(other.MainWindowHandle);
                    ShowWindow(other.MainWindowHandle, 9);
                }
                Shutdown();
                return;
            }

            base.OnStartup(e);
            ThemeService.Init();
            CreateTray();

            // --shot <png> [--theme frost --mode day]：把窗口按 96dpi 渲染成 PNG 后退出。
            // 走 RenderTargetBitmap 而不是屏幕截图：本机是 200% 缩放，屏幕截图要么拿到
            // 半个窗口放大、要么拿到垃圾矩形；离屏渲染得到的就是 1280×812 的 DIP 像素，
            // 正好和设计稿（1 CSS px = 1 DIP）逐像素比对。
            var args = Environment.GetCommandLineArgs();
            if (args.Contains("--shot"))
            {
                var path = args.SkipWhile(a => a != "--shot").Skip(1).FirstOrDefault()
                           ?? "shot.png";
                var theme = args.SkipWhile(a => a != "--theme").Skip(1).FirstOrDefault();
                var mode = args.SkipWhile(a => a != "--mode").Skip(1).FirstOrDefault();
                var size = args.SkipWhile(a => a != "--size").Skip(1).FirstOrDefault();
                if (!string.IsNullOrEmpty(theme)) ThemeService.SetTheme(theme);
                if (!string.IsNullOrEmpty(mode) && mode != ThemeService.Mode) ThemeService.ToggleMode();
                if (args.Contains("--open"))
                {
                    OpenWindowSelfCheck();
                }
                else if (args.Contains("--selftest-actions"))
                {
                    SelfTestActionsAndExit();
                }
                else if (args.Contains("--newinstance"))
                {
                    NewInstanceShotAndExit(path);
                }
                else if (args.Contains("--plugins"))
                {
                    PluginsShotAndExit(path);
                }
                else
                {
                    ShotAndExit(path, size);
                }
            }
        }
        catch (Exception ex)
        {
            Log("startup: " + ex);
            throw;
        }
    }

    private void ShotAndExit(string path, string size)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var win = new MainWindow();
        if (!string.IsNullOrEmpty(size))
        {
            var parts = size.Split('x');
            if (parts.Length == 2 && double.TryParse(parts[0], out var sw) &&
                double.TryParse(parts[1], out var sh))
            {
                win.Width = sw;
                win.Height = sh;
            }
        }
        win.Show();
        if (Environment.GetCommandLineArgs().Contains("--page") &&
            Environment.GetCommandLineArgs().SkipWhile(a => a != "--page").Skip(1).FirstOrDefault() == "settings")
        {
            win.OpenSettingsPage();
        }
        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(900) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            try
            {
                var w = (int)Math.Round(win.ActualWidth);
                var h = (int)Math.Round(win.ActualHeight);
                var rtb = new RenderTargetBitmap(w, h, 96, 96, PixelFormats.Pbgra32);
                rtb.Render(win);
                var enc = new PngBitmapEncoder();
                enc.Frames.Add(BitmapFrame.Create(rtb));
                using (var fs = File.Create(Path.GetFullPath(path)))
                    enc.Save(fs);
                Log($"shot -> {Path.GetFullPath(path)} ({w}x{h})");
            }
            catch (Exception ex)
            {
                Log("shot failed: " + ex);
            }
            win.Close();
            Shutdown();
        };
        timer.Start();
    }

    /// <summary>--plugins：只打开插件对话框并截图（开发期用来核对样式/数据）。</summary>
    /// <summary>--open：按当前发现的实例打开内置会话窗（自检用），10 秒后退出。</summary>
    private void OpenWindowSelfCheck()
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var list = DshDiscovery.Scan().ToList();
        DshDiscovery.AttachRunning(list);
        DshDiscovery.ApplyRegistryPorts(list);
        var inst = list.FirstOrDefault(i => i.Running) ?? list.FirstOrDefault();
        if (inst == null) { Log("[open] 没有可用实例"); Shutdown(); return; }
        var ok = DshHost.OpenWindow(inst, out var msg);
        Log("[open] " + inst.Label + " port=" + inst.Port + " -> " + (ok ? "OK" : "FAIL") + ": " + msg);
        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(10) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            Log("[open] titles=" + string.Join(" | ",
                System.Windows.Application.Current.Windows.Cast<Window>().Select(w => w.Title)));
            Shutdown();
        };
        timer.Start();
    }

    /// <summary>
    /// --selftest-actions：对发现的每个实例跑一遍「是否受管 / 修复自检」，
    /// 结果写进 crash.log（开发期用命令行验证动作层，不用点界面）。
    /// </summary>
    private void SelfTestActionsAndExit()
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        Task.Run(async () =>
        {
            var list = DshDiscovery.Scan().ToList();
            DshDiscovery.AttachRunning(list);
            DshDiscovery.ApplyRegistryPorts(list);
            foreach (var inst in list)
            {
                Log("[selftest] " + inst.Label + " | " + inst.Source + " | dir=" + inst.Dir
                    + " | managed=" + InstanceActions.IsManaged(inst)
                    + " | running=" + inst.Running + " port=" + inst.Port);
                var (ok, msg) = await InstanceActions.RepairAsync(inst, m => Log("    | " + m));
                Log("[selftest]   repair -> " + (ok ? "OK" : "FAIL") + ": " + msg);
            }
            Dispatcher.Invoke(Shutdown);
        });
    }

    /// <summary>--newinstance：只打开「新建实例」对话框并截图。</summary>
    private void NewInstanceShotAndExit(string path)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var win = new NewInstanceWindow();
        win.Show();
        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(900) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            try
            {
                var w = (int)Math.Round(win.ActualWidth);
                var h = (int)Math.Round(win.ActualHeight);
                var rtb = new RenderTargetBitmap(Math.Max(w, 1), Math.Max(h, 1), 96, 96, PixelFormats.Pbgra32);
                rtb.Render(win);
                var enc = new PngBitmapEncoder();
                enc.Frames.Add(BitmapFrame.Create(rtb));
                using (var fs = File.Create(Path.GetFullPath(path))) enc.Save(fs);
                Log($"newinstance shot -> {Path.GetFullPath(path)} ({w}x{h})");
            }
            catch (Exception ex) { Log("newinstance shot failed: " + ex); }
            win.Close();
            Shutdown();
        };
        timer.Start();
    }

    private void PluginsShotAndExit(string path)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var list = DshDiscovery.Scan().ToList();
        DshDiscovery.AttachRunning(list);
        var inst = list.FirstOrDefault();
        if (inst == null) { Log("no instance for plugins shot"); Shutdown(); return; }
        var win = new PluginWindow(inst);
        win.Show();
        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(5) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            try
            {
                var w = (int)Math.Round(win.ActualWidth);
                var h = (int)Math.Round(win.ActualHeight);
                var rtb = new RenderTargetBitmap(Math.Max(w, 1), Math.Max(h, 1), 96, 96, PixelFormats.Pbgra32);
                rtb.Render(win);
                var enc = new PngBitmapEncoder();
                enc.Frames.Add(BitmapFrame.Create(rtb));
                using (var fs = File.Create(Path.GetFullPath(path))) enc.Save(fs);
                Log($"plugins shot -> {Path.GetFullPath(path)} ({w}x{h})");
            }
            catch (Exception ex) { Log("plugins shot failed: " + ex); }
            win.Close();
            Shutdown();
        };
        timer.Start();
    }


    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int n);

    private void CreateTray()
    {
        try
        {
            _tray = new System.Windows.Forms.NotifyIcon
            {
                Icon = System.Drawing.SystemIcons.Application,
                Text = "DeepSeek Harness 管理器",
                Visible = true,
            };
            var menu = new System.Windows.Forms.ContextMenuStrip();
            menu.Items.Add("显示管理器", null, (_, _) => ShowMain());
            menu.Items.Add("退出", null, (_, _) => QuitForReal());
            _tray.ContextMenuStrip = menu;
            _tray.DoubleClick += (_, _) => ShowMain();
        }
        catch { _tray = null; }
    }

    private void ShowMain()
    {
        foreach (Window w in Windows)
        {
            if (w is MainWindow mw)
            {
                mw.Show();
                if (mw.WindowState == WindowState.Minimized) mw.WindowState = WindowState.Normal;
                mw.Activate();
                return;
            }
        }
    }

    private static void Log(string text)
    {
        try
        {
            Directory.CreateDirectory(LogDir);
            File.AppendAllText(Path.Combine(LogDir, "crash.log"),
                DateTime.Now.ToString("HH:mm:ss ") + text + Environment.NewLine);
        }
        catch { }
    }
}
