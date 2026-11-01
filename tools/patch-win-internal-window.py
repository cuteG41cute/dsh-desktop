"""打开窗口改成内置 WebView2 会话窗；加 --open 自检入口；删掉不再使用的外部启动器代码。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1) App：--open 自检（打开内置窗口并等待，把结果写 crash.log）
P_APP = os.path.join(ROOT, 'dsh-manager-win', 'App.xaml.cs')
APP_OLD = '                if (args.Contains("--selftest-actions"))'
APP_NEW = '''                if (args.Contains("--open"))
                {
                    OpenWindowSelfCheck();
                }
                else if (args.Contains("--selftest-actions"))'''
APP_METHOD_ANCHOR = '    /// <summary>\n    /// --selftest-actions'
APP_METHOD = '''    /// <summary>--open：按当前发现的实例打开内置会话窗（自检用），10 秒后退出。</summary>
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

''' + APP_METHOD_ANCHOR


def patch_app():
    src = io.open(P_APP, encoding='utf-8').read()
    if APP_OLD not in src or APP_METHOD_ANCHOR not in src:
        print('MISS app')
        return 1
    src = src.replace(APP_OLD, APP_NEW, 1)
    src = src.replace(APP_METHOD_ANCHOR, APP_METHOD, 1)
    io.open(P_APP, 'w', encoding='utf-8', newline='\n').write(src)
    print('app: --open')
    return 0


# 2) DshHost：删掉已经用不上的外部启动器辅助函数
P_HOST = os.path.join(ROOT, 'dsh-manager-win', 'Services', 'DshHost.cs')
HOST_START = '    private static string LauncherDir =>'
HOST_END = '    public static string LogPathFor(DshInstance inst)'


def patch_host():
    src = io.open(P_HOST, encoding='utf-8').read()
    if HOST_START not in src or HOST_END not in src:
        print('MISS host block')
        return 1
    start = src.index(HOST_START)
    end = src.index(HOST_END, start)
    src = src[:start] + src[end:]
    io.open(P_HOST, 'w', encoding='utf-8', newline='\n').write(src)
    print('host: removed external launcher helpers')
    return 0


# 3) 删掉外部启动器实现
def remove_desktop_launcher():
    p = os.path.join(ROOT, 'dsh-manager-win', 'Services', 'DesktopLauncher.cs')
    if os.path.exists(p):
        os.remove(p)
        print('removed DesktopLauncher.cs')
    return 0


if __name__ == '__main__':
    raise SystemExit(patch_app() or patch_host() or remove_desktop_launcher())
