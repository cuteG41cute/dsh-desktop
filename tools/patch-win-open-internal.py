"""DshHost.OpenWindow 改为走内置的 DesktopLauncher（不再调外部 launcher.ps1 / 浏览器）。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'Services', 'DshHost.cs')

START = '    /// <summary>\n    /// 打开窗口 = 调**桌面版启动器**（DSH Desktop），不是浏览器。'
END = '    private static string LauncherDir =>'

NEW = '''    /// <summary>
    /// 打开窗口 = 启动**桌面窗口**（DSH Desktop.exe）。
    /// 启动逻辑已经内置（Services/DesktopLauncher.cs），端口由管理器下发，
    /// 不再调用外部 launcher.ps1（那套会自己扫安装、自己挑端口）。
    /// </summary>
    public static bool OpenWindow(DshInstance inst, out string message)
    {
        return DesktopLauncher.Open(inst, out message);
    }

    private static string LauncherDir =>'''


def main():
    src = io.open(P, encoding='utf-8').read()
    start = src.index(START)
    end = src.index(END, start) + len(END)
    src = src[:start] + NEW + src[end:]
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('DshHost.OpenWindow -> DesktopLauncher')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
