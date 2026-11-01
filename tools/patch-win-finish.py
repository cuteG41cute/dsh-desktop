"""收尾一大批：单实例、托盘、关闭到托盘、快捷动作接线、帮助/关于、扫描性能。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_CS = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')
MAIN_XAML = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml')
APP = os.path.join(ROOT, 'dsh-manager-win', 'App.xaml.cs')
DISC = os.path.join(ROOT, 'dsh-manager-win', 'Services', 'DshDiscovery.cs')

# ---------------------------------------------------------------- 1) 扫描性能：一次拿所有 node 命令行
DISC_OLD = '''    private static string CommandLineOf(int pid)
    {
        try
        {
            var psi = new ProcessStartInfo("powershell",
                "-NoProfile -Command \\"(Get-CimInstance Win32_Process -Filter 'ProcessId=" + pid
                + "').CommandLine\\"")
            {
                RedirectStandardOutput = true, RedirectStandardError = true,
                UseShellExecute = false, CreateNoWindow = true,
            };
            using var p = Process.Start(psi);
            var text = p.StandardOutput.ReadToEnd();
            p.WaitForExit(6000);
            return text.Trim();
        }
        catch { return ""; }
    }'''

DISC_NEW = '''    /// <summary>
    /// 一次取回所有 node.exe 的 (PID, 命令行)，而不是每个端口起一次 PowerShell。
    /// 之前扫描 20 个端口要起 20 次 powershell（每次几百毫秒），界面打开明显卡。
    /// </summary>
    private static Dictionary<int, string> _cmdCache;
    private static DateTime _cmdCacheAt = DateTime.MinValue;

    private static Dictionary<int, string> NodeCommandLines()
    {
        if (_cmdCache != null && (DateTime.Now - _cmdCacheAt).TotalSeconds < 5) return _cmdCache;
        var map = new Dictionary<int, string>();
        try
        {
            var psi = new ProcessStartInfo("powershell",
                "-NoProfile -Command \\"Get-CimInstance Win32_Process -Filter \\\\\\"Name='node.exe'\\\\\\" "
                + "| ForEach-Object { \\\\\\"$($_.ProcessId)|$($_.CommandLine)\\\\\\" }\\"")
            {
                RedirectStandardOutput = true, RedirectStandardError = true,
                UseShellExecute = false, CreateNoWindow = true,
            };
            using var p = Process.Start(psi);
            var text = p.StandardOutput.ReadToEnd();
            p.WaitForExit(8000);
            foreach (var line in text.Split('\\n'))
            {
                var t = line.Trim();
                var bar = t.IndexOf('|');
                if (bar <= 0) continue;
                if (!int.TryParse(t.Substring(0, bar), out var pid)) continue;
                map[pid] = t.Substring(bar + 1);
            }
        }
        catch { }
        _cmdCache = map;
        _cmdCacheAt = DateTime.Now;
        return map;
    }

    private static string CommandLineOf(int pid) =>
        NodeCommandLines().TryGetValue(pid, out var cmd) ? cmd : "";'''

# ---------------------------------------------------------------- 2) 快捷动作 / 帮助 / 关于
XAML_PAIRS = [
    ('<Border x:Name="Quick1" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"',
     '<Border x:Name="Quick1" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"\n'
     '                                        MouseLeftButtonDown="OnQuickToken"'),
    ('<Border x:Name="Quick3" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"',
     '<Border x:Name="Quick3" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"\n'
     '                                        MouseLeftButtonDown="OnQuickUpdate"'),
    ('<Border x:Name="Quick4" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"',
     '<Border x:Name="Quick4" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"\n'
     '                                        MouseLeftButtonDown="OnQuickFolder"'),
    ('<Button Style="{StaticResource SideLink}" x:Name="HelpNav">',
     '<Button Style="{StaticResource SideLink}" x:Name="HelpNav" Click="OnHelp">'),
    ('<Button Style="{StaticResource IconBtn}" ToolTip="关于">',
     '<Button Style="{StaticResource IconBtn}" ToolTip="关于" Click="OnAbout">'),
]

CS_CODE = '''
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
        var text = "DeepSeek Harness 管理器\\n\\n"
                   + "版本 " + typeof(MainWindow).Assembly.GetName().Version + "\\n"
                   + ".NET " + Environment.Version + " · WPF + WebView2\\n"
                   + "DSH_HOME：" + DshDiscovery.HomeDir + "\\n\\n"
                   + "Windows 版：管理器与桌面窗口合为一体。\\n"
                   + "https://github.com/cuteG41cute/dsh-desktop";
        MessageBox.Show(this, text, "关于", MessageBoxButton.OK, MessageBoxImage.Information);
    }
'''

CS_ANCHOR = '    private void OnNewInstance(object sender, RoutedEventArgs e)'

# ---------------------------------------------------------------- 3) 单实例 + 托盘 + 关闭到托盘
APP_OLD_VARS = 'public partial class App : Application\n{'
APP_NEW_VARS = '''public partial class App : Application
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
'''

APP_SETUP_ANCHOR = '            base.OnStartup(e);'
APP_SETUP = '''            // ---- 单实例：已经有管理器在跑就把它提到前台，然后退出本次 ----
            _single = new System.Threading.Mutex(true, "Global\\\\DshManager", out var isNew);
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

''' + APP_SETUP_ANCHOR

APP_TRAY_ANCHOR = '            ThemeService.Init();'
APP_TRAY = '''            ThemeService.Init();
            CreateTray();'''

APP_TRAY_METHOD = '''
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
'''


def patch_file(path, pairs):
    src = io.open(path, encoding='utf-8').read()
    misses = []
    for old, new in pairs:
        if old not in src:
            misses.append(old.strip().splitlines()[0][:60])
            continue
        src = src.replace(old, new, 1)
    io.open(path, 'w', encoding='utf-8', newline='\n').write(src)
    return misses


def main():
    print('discovery:', patch_file(DISC, [(DISC_OLD, DISC_NEW)]))
    print('xaml:', patch_file(MAIN_XAML, XAML_PAIRS))
    main_cs = io.open(MAIN_CS, encoding='utf-8').read()
    if CS_ANCHOR not in main_cs:
        print('MISS cs anchor')
        return 1
    main_cs = main_cs.replace(CS_ANCHOR, CS_CODE + '\n' + CS_ANCHOR, 1)
    # 关闭到托盘
    main_cs = main_cs.replace(
        '    private void OnClose(object sender, RoutedEventArgs e) => Close();',
        '''    private void OnClose(object sender, RoutedEventArgs e)
    {
        // 点 X = 收进托盘（和旧桌面版一致），真正退出走托盘菜单
        var app = (App)Application.Current;
        if (app.Quitting) { Close(); return; }
        Hide();
    }''')
    io.open(MAIN_CS, 'w', encoding='utf-8', newline='\n').write(main_cs)
    print('main cs patched')

    print('app:', patch_file(APP, [
        (APP_OLD_VARS, APP_NEW_VARS),
        (APP_SETUP_ANCHOR, APP_SETUP),
        (APP_TRAY_ANCHOR, APP_TRAY),
    ]))
    # 托盘方法插到类尾（Log 方法之前）
    app_src = io.open(APP, encoding='utf-8').read()
    if 'private void CreateTray' not in app_src:
        anchor = '    private static void Log(string text)'
        app_src = app_src.replace(anchor, APP_TRAY_METHOD + '\n' + anchor, 1)
        io.open(APP, 'w', encoding='utf-8', newline='\n').write(app_src)
        print('tray method added')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
