using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace DshManager.Services;

/// <summary>一个可管理的 DSH 安装（Windows 上没有 Linux 那种「便携实例」，所以按安装来源区分）。</summary>
public sealed class DshInstance
{
    public string Id { get; init; }
    public string Label { get; init; }
    /// <summary>dsh 入口：<c>.../@deepseek-ai/dsh/lib/bin.js</c></summary>
    public string Entry { get; init; }
    public string NodeExe { get; init; }
    public string Source { get; init; }          // 「npx 缓存」/「全局安装」/「profile」/「PATH」
    public int Port { get; set; } = 0;          // 0 = 还没分配（安装本身不带端口）
    public bool Running { get; set; }
    public int Pid { get; set; }
    public string DshVersion { get; set; } = "";
    public string NodeVersion { get; set; } = "";
    public string Home { get; init; }            // DSH_HOME
    public string Dir { get; init; }            // 安装目录（<dir>/node_modules/@deepseek-ai/dsh）
    public string LogPath { get; init; }
    public int SortKey { get; init; }
}

/// <summary>
/// 发现本机的 DSH 安装 + 启停服务 + 读日志。
/// 发现顺序照搬安装器/启动器（msi/payload/launcher.ps1）那套：npx 缓存 → 全局 npm → profile → PATH。
/// </summary>
public static class DshDiscovery
{
    public static string HomeDir =>
        Environment.GetEnvironmentVariable("DSH_HOME")
        ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".dsh");

    private static string LocalAppData => Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
    private static string AppData => Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
    private static string UserProfile => Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);

    public static IReadOnlyList<DshInstance> Scan()
    {
        var found = new List<DshInstance>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        void Add(string entry, string source, int sort, string labelOverride = null)
        {
            if (string.IsNullOrWhiteSpace(entry) || !File.Exists(entry)) return;
            var root = Path.GetFullPath(entry);
            if (!seen.Add(root)) return;
            var label = string.IsNullOrWhiteSpace(labelOverride) ? NameFor(root) : labelOverride;
            if (source == "npx 缓存")
            {
                // .../_npx/<hash>/node_modules/@deepseek-ai/dsh/lib/bin.js → 往上 5 层才是 <hash>
                var h = Path.GetDirectoryName(entry) ?? "";
                for (var i = 0; i < 5 && !string.IsNullOrEmpty(h); i++) h = Path.GetDirectoryName(h) ?? "";
                var hashDir = Path.GetFileName(h);
                if (!string.IsNullOrEmpty(hashDir)) label += " (" + (hashDir.Length > 10 ? hashDir.Substring(0, 10) : hashDir) + ")";
            }
            found.Add(new DshInstance
            {
                Id = MakeId(root, source),
                Label = label,
                Entry = root,
                NodeExe = FindNodeNear(root)
                          ?? PortableNodeOf(InstallRootOf(root))
                          ?? FindNodeOnPath(),
                Source = source,
                Home = DshHomeOf(InstallRootOf(root)),
                Dir = InstallRootOf(root),
                LogPath = Path.Combine(LocalAppData, "dsh-manager", "logs", MakeId(root, source) + ".log"),
                SortKey = sort,
            });
        }

        // 1) npx 缓存（本机现在跑的就是这个）
        var npxRoot = Path.Combine(LocalAppData, "npm-cache", "_npx");
        if (Directory.Exists(npxRoot))
        {
            foreach (var dir in Directory.GetDirectories(npxRoot))
                Add(Path.Combine(dir, "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js"), "npx 缓存", 10);
        }

        // 1b) pi-node（本机 where dsh 指向这里）
        Add(Path.Combine(LocalAppData, "pi-node", "current", "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js"),
            "pi-node", 15);

        // 2) 全局 npm 安装
        Add(Path.Combine(AppData, "npm", "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js"), "全局安装", 20);
        Add(Path.Combine(ProgramFiles(), "nodejs", "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js"), "全局安装", 21);

        // 3) profile 里随实例装的
        var profiles = Path.Combine(HomeDir, "profiles");
        if (Directory.Exists(profiles))
        {
            foreach (var dir in Directory.GetDirectories(profiles))
                Add(Path.Combine(dir, "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js"), "profile", 30);
        }

        // 4) PATH 上的 dsh（.cmd 里能读出真实入口）
        var pathEntry = FindFromPath();
        if (!string.IsNullOrEmpty(pathEntry)) Add(pathEntry, "PATH", 40);

        // 5) 管理器自己创建的实例（自定义目录，固定扫描位置扫不到）
        foreach (var reg in InstanceRegistry.Load())
        {
            if (string.IsNullOrWhiteSpace(reg.Dir)) continue;
            if (!Directory.Exists(reg.Dir)) continue;   // 目录被手动删了就跳过
            Add(Path.Combine(reg.Dir, "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js"),
                "管理器创建", 5, string.IsNullOrWhiteSpace(reg.Label)
                    ? System.IO.Path.GetFileName(reg.Dir.TrimEnd('\\')) : reg.Label);
        }

        foreach (var inst in found)
        {
            inst.DshVersion = ReadVersion(inst.Entry);
            inst.NodeVersion = ReadNodeVersion(inst.NodeExe);
            Probe(inst);
        }
        return found.OrderBy(i => i.SortKey).ThenBy(i => i.Label).ToList();
    }

    private static string ProgramFiles() =>
        Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);

    private static string NameFor(string entry)
    {
        // 取 …/@deepseek-ai/dsh/lib/bin.js 的上一层里可读的名字；npx 的哈希目录不友好，用来源名
        var dir = Path.GetDirectoryName(entry) ?? "";
        var pkg = Path.GetFullPath(Path.Combine(dir, ".."));
        try
        {
            var meta = ReadJson(Path.Combine(pkg, "package.json"));
            var name = meta.TryGetProperty("name", out var n) ? n.GetString() : null;
            if (!string.IsNullOrEmpty(name)) return name;
        }
        catch { }
        return "DeepSeek Harness";
    }

    /// <summary>
    /// 实例自己的 DSH_HOME：&lt;安装根&gt;\dsh-home。
    /// 存在就用它（会话/工作区/插件/凭据都在里面，实例之间互不可见）；
    /// 不存在就沿用全局 %USERPROFILE%\.dsh（老实例的兼容路径）。
    /// </summary>
    private static string DshHomeOf(string installRoot)
    {
        try
        {
            if (!string.IsNullOrEmpty(installRoot))
            {
                var home = Path.Combine(installRoot, "dsh-home");
                if (Directory.Exists(home)) return home;
            }
        }
        catch { }
        return HomeDir;
    }

    /// <summary>管理器给实例装的便携 Node（&lt;安装根&gt;\node\node.exe）。</summary>
    private static string PortableNodeOf(string installRoot)
    {
        try
        {
            if (string.IsNullOrEmpty(installRoot)) return null;
            var exe = Path.Combine(installRoot, "node", "node.exe");
            return File.Exists(exe) ? exe : null;
        }
        catch { return null; }
    }

    private static string MakeId(string entry, string source)
    {
        var dir = Path.GetDirectoryName(entry) ?? entry;
        return source + "@" + StableHash(dir);
    }

    /// <summary>
    /// 稳定的短哈希：string.GetHashCode() 在 .NET 里每个进程都不一样，
    /// 用它做实例 id 会让日志文件名每次都变（旧日志再也对不上）。
    /// </summary>
    internal static string StableHash(string text)
    {
        try
        {
            using var sha = System.Security.Cryptography.SHA1.Create();
            var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes((text ?? "").ToLowerInvariant()));
            return Convert.ToHexString(bytes, 0, 4).ToLowerInvariant();
        }
        catch
        {
            return Math.Abs((text ?? "").Length).ToString("x");
        }
    }

    /// <summary>
    /// 安装根目录：入口是 …\node_modules\@deepseek-ai\dsh\lib\bin.js，
    /// 根就是 node_modules 的上一层（npx 缓存 → …\_npx\&lt;hash&gt;，管理器创建 → 安装目录）。
    /// 管理器登记表里存的是这个根，两边必须对得上，否则「管理器创建的实例」会被当成系统安装。
    /// </summary>
    private static string InstallRootOf(string entry)
    {
        if (string.IsNullOrEmpty(entry)) return "";
        var marker = Path.DirectorySeparatorChar + "node_modules" + Path.DirectorySeparatorChar;
        var idx = entry.LastIndexOf(marker, StringComparison.OrdinalIgnoreCase);
        if (idx > 0) return Path.GetFullPath(entry.Substring(0, idx));
        var dir = Path.GetDirectoryName(entry) ?? "";
        return Path.GetFullPath(Path.Combine(dir, ".."));
    }

    private static string FindNodeNear(string entry)
    {
        // 常见布局：<prefix>/node/bin/node.exe 或 …/node.exe 在入口附近
        var dir = Path.GetDirectoryName(entry) ?? "";
        for (var i = 0; i < 6 && !string.IsNullOrEmpty(dir); i++)
        {
            foreach (var cand in new[]
                     {
                         Path.Combine(dir, "node.exe"),
                         Path.Combine(dir, "node", "node.exe"),
                         Path.Combine(dir, "node", "bin", "node.exe"),
                     })
            {
                if (File.Exists(cand)) return cand;
            }
            dir = Path.GetDirectoryName(dir) ?? "";
        }
        return null;
    }

    private static string FindNodeOnPath()
    {
        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var part in path.Split(';'))
        {
            if (string.IsNullOrWhiteSpace(part)) continue;
            var cand = Path.Combine(part.Trim(), "node.exe");
            if (File.Exists(cand)) return cand;
        }
        return null;
    }

    private static string FindFromPath()
    {
        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var part in path.Split(';'))
        {
            if (string.IsNullOrWhiteSpace(part)) continue;
            var baseDir = part.Trim();
            // npm 生成的是 dsh.cmd，内容里有真实 bin.js 路径
            var cmd = Path.Combine(baseDir, "dsh.cmd");
            if (File.Exists(cmd))
            {
                try
                {
                    // dsh.cmd 里通常长这样：
                    //   @IF EXIST "%~dp0\node.exe" ( "%~dp0\node.exe" "%~dp0\node_modules\@deepseek-ai\dsh\lib\bin.js" %* )
                    // 不写正则（转义太容易错），直接找含 bin.js 的那行，取它两侧的引号。
                    foreach (var line in File.ReadAllLines(cmd))
                    {
                        var idx = line.IndexOf("dsh\\lib\\bin.js", StringComparison.OrdinalIgnoreCase);
                        if (idx < 0) continue;
                        var open = line.LastIndexOf('"', idx);
                        var close = line.IndexOf('"', idx);
                        if (open >= 0 && close > open)
                        {
                            var binPath = line.Substring(open + 1, close - open - 1);
                            return binPath.Replace("%~dp0", baseDir + "\\");
                        }
                    }
                }
                catch { }
            }
        }
        return null;
    }

    private static JsonElement ReadJson(string path)
    {
        var raw = File.ReadAllBytes(path);
        var text = Encoding.UTF8.GetString(raw).TrimStart('\uFEFF');
        return JsonDocument.Parse(text).RootElement.Clone();
    }

    private static string ReadVersion(string entry)
    {
        try
        {
            var pkg = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(entry) ?? "", ".."));
            var meta = ReadJson(Path.Combine(pkg, "package.json"));
            return meta.TryGetProperty("version", out var v) ? (v.GetString() ?? "") : "";
        }
        catch { return ""; }
    }

    private static readonly Dictionary<string, string> NodeVerCache = new();

    private static string ReadNodeVersion(string nodeExe)
    {
        if (string.IsNullOrEmpty(nodeExe) || !File.Exists(nodeExe)) return "";
        lock (NodeVerCache)
        {
            if (NodeVerCache.TryGetValue(nodeExe, out var cached)) return cached;
            try
            {
                var psi = new ProcessStartInfo(nodeExe, "--version")
                {
                    RedirectStandardOutput = true, UseShellExecute = false,
                    CreateNoWindow = true,
                };
                using var p = Process.Start(psi);
                var text = p.StandardOutput.ReadToEnd().Trim();
                p.WaitForExit(4000);
                var ver = text.TrimStart('v');
                NodeVerCache[nodeExe] = ver;
                return ver;
            }
            catch { return ""; }
        }
    }

    private static int PickPort(int start)
    {
        for (var port = start; port < start + 40; port++)
        {
            var l = new TcpListener(System.Net.IPAddress.Loopback, port);
            try
            {
                l.Start();
                l.Stop();
                return port;
            }
            catch { }
        }
        return start;
    }

    /// <summary>
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

    /// <summary>没在跑的登记实例，把当初分配的端口填回去（启动时直接复用）。</summary>
    public static void ApplyRegistryPorts(IList<DshInstance> list)
    {
        var regs = InstanceRegistry.Load();
        foreach (var inst in list)
        {
            if (inst.Running || inst.Port > 0) continue;
            var reg = regs.FirstOrDefault(r => string.Equals(
                Path.GetFullPath(r.Dir ?? ""), Path.GetFullPath(inst.Dir ?? ""), StringComparison.OrdinalIgnoreCase));
            if (reg != null && reg.Port > 0) inst.Port = reg.Port;
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
        var idx = cmd.IndexOf("lib\\bin.js", StringComparison.OrdinalIgnoreCase);
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

    /// <summary>
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
                "-NoProfile -Command \"Get-CimInstance Win32_Process -Filter \\\"Name='node.exe'\\\" "
                + "| ForEach-Object { \\\"$($_.ProcessId)|$($_.CommandLine)\\\" }\"")
            {
                RedirectStandardOutput = true, RedirectStandardError = true,
                UseShellExecute = false, CreateNoWindow = true,
            };
            using var p = Process.Start(psi);
            var text = p.StandardOutput.ReadToEnd();
            p.WaitForExit(8000);
            foreach (var line in text.Split('\n'))
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
        NodeCommandLines().TryGetValue(pid, out var cmd) ? cmd : "";

    /// <summary>用 netstat -ano 找监听该端口的 PID（不引入 WMI 依赖）。</summary>
    public static int FindPidByPort(int port)
    {
        try
        {
            var psi = new ProcessStartInfo("netstat", "-ano -p tcp")
            {
                RedirectStandardOutput = true, UseShellExecute = false, CreateNoWindow = true,
            };
            using var p = Process.Start(psi);
            var text = p.StandardOutput.ReadToEnd();
            p.WaitForExit(4000);
            foreach (var line in text.Split('\n'))
            {
                var t = line.Trim();
                if (!t.StartsWith("TCP")) continue;
                if (!t.Contains(":" + port + " ")) continue;
                if (!t.Contains("LISTENING")) continue;
                var parts = t.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length >= 5 && int.TryParse(parts[^1], out var pid)) return pid;
            }
        }
        catch { }
        return 0;
    }
}
