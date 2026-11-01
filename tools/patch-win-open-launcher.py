"""「打开窗口」改成调桌面版启动器（wscript + .vbs），而不是丢给浏览器。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'Services', 'DshHost.cs')

OLD = '''    /// <summary>打开 WebUI：优先用系统默认浏览器（后续可换成内置 WebView2 窗口）。</summary>
    public static bool OpenWindow(DshInstance inst, out string message)
    {
        message = "";
        if (!inst.Running)
        {
            message = "服务没在运行，先启动服务";
            return false;
        }
        var url = "http://127.0.0.1:" + inst.Port + "/";
        try
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            message = "已在默认浏览器打开 " + url;
            return true;
        }
        catch (Exception ex)
        {
            message = "打开失败：" + ex.Message;
            return false;
        }
    }'''

NEW = '''    /// <summary>
    /// 打开窗口 = 调**桌面版启动器**（DSH Desktop），不是浏览器。
    /// 启动器自己负责：确保服务在跑 → 用 WebView2 开一个应用窗口（无地址栏、单实例、X 收进托盘）。
    /// 所以这里不做别的，把启动器拉起来即可；它已经在跑就只会把那个窗口提到前台。
    /// </summary>
    public static bool OpenWindow(DshInstance inst, out string message)
    {
        message = "";

        var vbs = FindLauncherVbs();
        if (!string.IsNullOrEmpty(vbs))
        {
            try
            {
                // wscript 跑 .vbs：全程无控制台窗口（这是启动器官方推荐入口）
                Process.Start(new ProcessStartInfo("wscript.exe", "\\"" + vbs + "\\"")
                {
                    UseShellExecute = true,
                    CreateNoWindow = true,
                    WorkingDirectory = Path.GetDirectoryName(vbs) ?? "",
                });
                message = "已通过桌面版启动器打开窗口";
                return true;
            }
            catch (Exception ex)
            {
                message = "启动桌面版失败：" + ex.Message;
            }
        }

        var ps1 = FindLauncherPs1();
        if (!string.IsNullOrEmpty(ps1))
        {
            try
            {
                Process.Start(new ProcessStartInfo("powershell",
                    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \\"" + ps1 + "\\"")
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WorkingDirectory = Path.GetDirectoryName(ps1) ?? "",
                });
                message = "已通过 launcher.ps1 打开窗口";
                return true;
            }
            catch (Exception ex)
            {
                message = "启动 launcher.ps1 失败：" + ex.Message;
            }
        }

        // 兜底：没装桌面版就给浏览器，并说明原因
        var url = "http://127.0.0.1:" + inst.Port + "/";
        try
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            message = "没找到桌面版启动器，已用浏览器打开 " + url;
            return true;
        }
        catch (Exception ex)
        {
            message = "打开失败：" + ex.Message + "（也没找到桌面版启动器）";
            return false;
        }
    }

    private static string LauncherDir =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs", "DSH Desktop");

    /// <summary>启动器入口：优先中文名，其次英文名（两者内容一致）。</summary>
    private static string FindLauncherVbs()
    {
        var dir = LauncherDir;
        foreach (var name in new[] { "启动 DeepSeek Harness.vbs", "Start DeepSeek Harness.vbs" })
        {
            var p = Path.Combine(dir, name);
            if (File.Exists(p)) return p;
        }
        return "";
    }

    private static string FindLauncherPs1()
    {
        var p = Path.Combine(LauncherDir, "launcher.ps1");
        if (File.Exists(p)) return p;
        // 开发目录里的那份
        var dir = AppContext.BaseDirectory;
        for (var i = 0; i < 6 && !string.IsNullOrEmpty(dir); i++)
        {
            var cand = Path.Combine(dir, "dsh-desktop", "msi", "payload", "launcher.ps1");
            if (File.Exists(cand)) return cand;
            dir = Path.GetDirectoryName(dir.TrimEnd(Path.DirectorySeparatorChar)) ?? "";
        }
        return "";
    }'''

ANCHOR = '    public static string LogPathFor(DshInstance inst)'


def main():
    src = io.open(P, encoding='utf-8').read()
    if OLD not in src:
        print('MISS open window')
        return 1
    src = src.replace(OLD, NEW, 1)
    if ANCHOR not in src:
        print('MISS anchor')
        return 1
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('open via desktop launcher')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
