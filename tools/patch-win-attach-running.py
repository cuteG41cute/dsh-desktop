"""修「哪个实例在跑」的判定：端口不再人人 3080。

之前每个 DshInstance 默认 Port=3080，于是探活时全都显示运行中。
现在：安装本身不带端口 → 扫完再 AttachRunning() 反查谁在监听、监听的是哪个 bin.js；
端口选择持久化到 %APPDATA%\\dsh-manager\\instances.json，启动时分配空闲端口。
"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'Services', 'DshDiscovery.cs')

# 1) 默认端口去掉
OLD_PORT = '    public int Port { get; set; } = 3080;'
NEW_PORT = '    public int Port { get; set; } = 0;          // 0 = 还没分配（安装本身不带端口）'

# 2) Probe 逻辑改成「没端口就算没跑」
OLD_PROBE = '''    /// <summary>探活：端口能连上就算运行中，并尽量从进程表里认出 PID。</summary>
    public static void Probe(DshInstance inst)
    {
        inst.Running = false;
        inst.Pid = 0;
        try
        {
            using var c = new TcpClient();
            var task = c.ConnectAsync("127.0.0.1", inst.Port < 1 ? 3080 : inst.Port);
            if (task.Wait(500) && c.Connected)
            {
                inst.Running = true;
                inst.Pid = FindPidByPort(inst.Port);
            }
        }
        catch { }
    }'''

NEW_PROBE = '''    /// <summary>
    /// 探活：只看这个实例**自己的端口**（没分配端口=没在跑）。
    /// 以前所有实例都用 3080 探活，结果「全都显示运行中」——本机 3 个安装同时点亮。
    /// </summary>
    public static void Probe(DshInstance inst)
    {
        inst.Running = false;
        inst.Pid = 0;
        if (inst.Port <= 0) return;
        try
        {
            using var c = new TcpClient();
            var task = c.ConnectAsync("127.0.0.1", inst.Port);
            if (task.Wait(600) && c.Connected)
            {
                inst.Running = true;
                inst.Pid = FindPidByPort(inst.Port);
            }
        }
        catch { }
    }

    /// <summary>
    /// 反查本机正在跑的 DSH：谁在监听 3080..3099，命令行里的 bin.js 是哪个安装。
    /// 匹配上的实例获得 Port/Pid/Running——这样「当前用的是哪个」是查出来的，不是猜的。
    /// </summary>
    public static void AttachRunning(IList<DshInstance> list)
    {
        foreach (var inst in list)
        {
            inst.Port = 0;
            inst.Pid = 0;
            inst.Running = false;
        }
        for (var port = 3080; port <= 3099; port++)
        {
            if (!PortListening(port)) continue;
            var pid = FindPidByPort(port);
            if (pid <= 0) continue;
            var cmd = CommandLineOf(pid);
            var entry = ExtractEntry(cmd);
            if (string.IsNullOrEmpty(entry)) continue;
            var match = list.FirstOrDefault(i => PathEquals(i.Entry, entry));
            if (match == null) continue;           // 跑的是管理器没扫到的安装，先不认领
            match.Port = port;
            match.Pid = pid;
            match.Running = true;
        }
    }

    private static bool PortListening(int port)
    {
        try
        {
            using var c = new TcpClient();
            var t = c.ConnectAsync("127.0.0.1", port);
            return t.Wait(300) && c.Connected;
        }
        catch { return false; }
    }

    private static bool PathEquals(string a, string b)
    {
        try
        {
            return string.Equals(Path.GetFullPath(a), Path.GetFullPath(b), StringComparison.OrdinalIgnoreCase);
        }
        catch { return false; }
    }

    /// <summary>从命令行里抠出 bin.js 的绝对路径。</summary>
    private static string ExtractEntry(string cmd)
    {
        if (string.IsNullOrEmpty(cmd)) return "";
        var marker = "dsh\\\\lib\\\\bin.js";
        var idx = cmd.IndexOf("lib\\\\bin.js", StringComparison.OrdinalIgnoreCase);
        if (idx < 0) return "";
        // 向前找到路径起点（引号或空格之后）
        var start = cmd.LastIndexOf('"', idx);
        if (start >= 0)
        {
            var end = cmd.IndexOf('"', idx);
            if (end > start) return cmd.Substring(start + 1, end - start - 1);
        }
        var space = cmd.LastIndexOf(' ', idx);
        var endSpace = cmd.IndexOf(' ', idx);
        if (endSpace < 0) endSpace = cmd.Length;
        return space >= 0 ? cmd.Substring(space + 1, endSpace - space - 1) : "";
    }

    private static string CommandLineOf(int pid)
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


def main():
    src = io.open(P, encoding='utf-8').read()
    for old, new in ((OLD_PORT, NEW_PORT), (OLD_PROBE, NEW_PROBE)):
        if old not in src:
            print('MISS:', old.splitlines()[0][:60])
            return 1
        src = src.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('discovery: attach running by port+cmdline')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
