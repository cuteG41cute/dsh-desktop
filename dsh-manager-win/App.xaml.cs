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
                if (other != null)
                {
                    // 已经有管理器在跑：把它的窗口弄出来。
                    // 点过 X 收进托盘时窗口是**隐藏**的，MainWindowHandle 会返回 0，
                    // 只看它就会「什么都没发生」——用户看到的就是「程序启动不了」。
                    var hwnd = other.MainWindowHandle;
                    if (hwnd == IntPtr.Zero) hwnd = FindManagerWindow(other.Id);
                    if (hwnd != IntPtr.Zero)
                    {
                        ShowWindow(hwnd, 9);          // SW_RESTORE
                        ShowWindow(hwnd, 5);          // SW_SHOW（托盘隐藏后必须显式显示）
                        SetForegroundWindow(hwnd);
                        SetWindowPos(hwnd, new IntPtr(-1), 0, 0, 0, 0, 0x0003); // 顶一下
                        SetWindowPos(hwnd, new IntPtr(-2), 0, 0, 0, 0, 0x0003); // 再取消置顶
                    }
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
            // --open [--open-hold 秒]：按当前发现的实例打开内置会话窗，到时自动退出（自检用）。
            // 单独用，不用配 --shot：会话窗里是 WebView2 原生子窗口，离屏渲染拍不到。
            if (args.Contains("--open"))
            {
                var hold = args.SkipWhile(a => a != "--open-hold").Skip(1).FirstOrDefault();
                OpenWindowSelfCheck(int.TryParse(hold, out var holdSeconds) ? holdSeconds : 10);
                return;
            }
            // --selftest-install <dir>：真装一份实例，然后依次跑 修复/更新/卸载，结果写 crash.log。
            // 用来在没有界面的情况下走一遍「管理器创建的实例」的完整生命周期。
            if (args.Contains("--selftest-install"))
            {
                var dir = args.SkipWhile(a => a != "--selftest-install").Skip(1).FirstOrDefault();
                SelfTestInstallAndExit(dir ?? "");
                return;
            }
            if (args.Contains("--shot"))
{
                var path = args.SkipWhile(a => a != "--shot").Skip(1).FirstOrDefault()
                           ?? "shot.png";
                var theme = args.SkipWhile(a => a != "--theme").Skip(1).FirstOrDefault();
                var mode = args.SkipWhile(a => a != "--mode").Skip(1).FirstOrDefault();
                var size = args.SkipWhile(a => a != "--size").Skip(1).FirstOrDefault();
                if (!string.IsNullOrEmpty(theme)) ThemeService.SetTheme(theme);
                if (!string.IsNullOrEmpty(mode) && mode != ThemeService.Mode) ThemeService.ToggleMode();
                if (args.Contains("--selftest-actions"))
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
                return;
            }

            // 正常启动：管理器主窗口。README 里的 StartupUri 已经去掉，
            // 命令行模式（--open/--shot/…）就不会顺带弹一个管理器窗口出来。
            var main = new MainWindow();
            main.Show();
        }
        catch (Exception ex)
        {
            Log("startup: " + ex);
            throw;
        }
    }

    /// <summary>
    /// --selftest-install &lt;dir&gt;：装一份实例，然后依次跑 修复 / 更新 / 卸载。
    /// 结果写进 crash.log（开发期验证「管理器创建的实例」这套动作，不用点界面）。
    /// </summary>
    private void SelfTestInstallAndExit(string dir)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        Task.Run(async () =>
        {
            try
            {
                if (string.IsNullOrWhiteSpace(dir))
                {
                    dir = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "dsh-manager", "instances", "selftest");
                    Log("[install-test] 没给目录，用默认：" + dir);
                }
                Log("[install-test] dir=" + dir);
                var binJs = Path.Combine(dir, "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js");
                if (File.Exists(binJs))
                {
                    Log("[install-test] 目录里已经有安装，跳过 npm install");
                }
                else
                {
                    var (iok, imsg) = await InstanceInstaller.InstallAsync(
                        dir, "latest", m => Log("    npm | " + m), 0);
                    Log("[install-test] install -> " + (iok ? "OK" : "FAIL") + ": " + imsg);
                    if (!iok) return;
                }

                var list = DshDiscovery.Scan().ToList();
                DshDiscovery.AttachRunning(list);
                var inst = list.FirstOrDefault(i => string.Equals(
                    Path.GetFullPath(i.Dir ?? ""), Path.GetFullPath(dir), StringComparison.OrdinalIgnoreCase));
                if (inst == null)
                {
                    Log("[install-test] 扫描没找到这个实例（发现 " + list.Count + " 个）");
                    foreach (var i in list) Log("[install-test]   saw " + i.Label + " dir=" + i.Dir);
                    return;
                }
                Log("[install-test] found " + inst.Label + " ver=" + inst.DshVersion
                    + " managed=" + InstanceActions.IsManaged(inst) + " entry=" + inst.Entry);

                var (rok, rmsg) = await InstanceActions.RepairAsync(inst, m => Log("    repair | " + m));
                Log("[install-test] repair -> " + (rok ? "OK" : "FAIL") + ": " + rmsg);

                var (uok, umsg) = await InstanceActions.UpdateAsync(inst, m => Log("    update | " + m));
                Log("[install-test] update -> " + (uok ? "OK" : "FAIL") + ": " + umsg);

                var (dok, dmsg) = InstanceActions.Uninstall(inst, deleteDir: true);
                Log("[install-test] uninstall -> " + (dok ? "OK" : "FAIL") + ": " + dmsg);
            }
            catch (Exception ex)
            {
                Log("[install-test] 异常：" + ex);
            }
            finally
            {
                Dispatcher.Invoke(Shutdown);
            }
        });
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
    /// <summary>--open [--open-hold 秒]：按当前发现的实例打开内置会话窗（自检用），到时退出。</summary>
    private void OpenWindowSelfCheck(int holdSeconds = 10)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var list = DshDiscovery.Scan().ToList();
        DshDiscovery.AttachRunning(list);
        DshDiscovery.ApplyRegistryPorts(list);
        var inst = list.FirstOrDefault(i => i.Running) ?? list.FirstOrDefault();
        if (inst == null) { Log("[open] 没有可用实例"); Shutdown(); return; }
        var ok = DshHost.OpenWindow(inst, out var msg);
        Log("[open] " + inst.Label + " port=" + inst.Port + " -> " + (ok ? "OK" : "FAIL") + ": " + msg);
        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(Math.Max(2, holdSeconds)) };
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

    // ---------------------------------------------------------------- 找已运行实例的窗口
    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern int GetWindowTextW(IntPtr hWnd, System.Text.StringBuilder text, int max);

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern int GetClassNameW(IntPtr hWnd, System.Text.StringBuilder text, int max);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

    /// <summary>
    /// 在指定进程的所有顶层窗口里找管理器主窗口（托盘隐藏时也能找到）：
    /// 优先标题里带「管理器」的，其次任意有标题的 DshManager 窗口。
    /// </summary>
    private static IntPtr FindManagerWindow(int pid)
    {
        IntPtr fallback = IntPtr.Zero;
        EnumWindows((h, _) =>
        {
            uint owner;
            GetWindowThreadProcessId(h, out owner);
            if (owner != (uint)pid) return true;
            var cls = new System.Text.StringBuilder(256);
            GetClassNameW(h, cls, 256);
            if (cls.ToString().IndexOf("DshManager", StringComparison.OrdinalIgnoreCase) < 0) return true;
            var text = new System.Text.StringBuilder(512);
            GetWindowTextW(h, text, 512);
            var title = text.ToString();
            if (title.Contains("管理器"))
            {
                fallback = h;
                return false;            // 找到主窗口，停
            }
            if (fallback == IntPtr.Zero && !string.IsNullOrWhiteSpace(title)) fallback = h;
            return true;
        }, IntPtr.Zero);
        return fallback;
    }

    /// <summary>
    /// 托盘图标：优先取 exe 里嵌入的应用图标（128/256 那档缩到 32 才清楚）。
    /// 取不到就退回系统默认图标，绝不因为图标缺失而起不来。
    /// </summary>
    private static System.Drawing.Icon TrayIconOf()
    {
        try
        {
            var exe = System.Diagnostics.Process.GetCurrentProcess().MainModule?.FileName;
            if (!string.IsNullOrEmpty(exe))
            {
                var small = System.Drawing.Icon.ExtractAssociatedIcon(exe);
                if (small != null)
                {
                    var bmp = small.ToBitmap();
                    var scaled = new System.Drawing.Bitmap(bmp, 32, 32);
                    return System.Drawing.Icon.FromHandle(scaled.GetHicon());
                }
            }
        }
        catch { }
        return System.Drawing.SystemIcons.Application;
    }

    private void CreateTray()
    {
        try
        {
            _tray = new System.Windows.Forms.NotifyIcon
            {
                // 托盘图标用 exe 自己的图标（黑鲸鱼），别用系统的默认程序图标
            Icon = TrayIconOf(),
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
