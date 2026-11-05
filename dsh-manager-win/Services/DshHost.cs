using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;

namespace DshManager.Services;

/// <summary>启停 DSH 服务、打开 WebUI、读日志。进程由管理器自己拉起时才有 stdout 日志。</summary>
public static class DshHost
{
    private sealed class Running
    {
        public Process Process;
        public readonly object Gate = new();
    }

    private static readonly Dictionary<string, Running> Started = new(StringComparer.OrdinalIgnoreCase);
    private static readonly object Gate = new();

    public static string LogDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "dsh-manager", "logs");

    public static bool Start(DshInstance inst, out string message)
    {
        message = "";
        if (string.IsNullOrEmpty(inst.NodeExe) || !File.Exists(inst.NodeExe))
        {
            message = "找不到 node.exe（这个安装没有自带 Node，PATH 上也没有）";
            return false;
        }
        if (string.IsNullOrEmpty(inst.Entry) || !File.Exists(inst.Entry))
        {
            message = "找不到 dsh 入口（bin.js）";
            return false;
        }

        DshDiscovery.InvalidateListeners();
        DshDiscovery.Probe(inst);
        if (inst.Running)
        {
            message = "服务已经在运行（端口 " + inst.Port + "）";
            return true;
        }

        inst.Port = PickPort(inst.Port);
        // 记住这次分配的端口（管理器创建的实例），下次启动/界面显示都用它
        var reg = InstanceRegistry.Load().FirstOrDefault(r => string.Equals(
            System.IO.Path.GetFullPath(r.Dir ?? ""), System.IO.Path.GetFullPath(inst.Dir ?? ""),
            StringComparison.OrdinalIgnoreCase));
        if (reg != null && reg.Port != inst.Port) { reg.Port = inst.Port; InstanceRegistry.Add(reg); }
        Directory.CreateDirectory(LogDir);
        var log = LogPathFor(inst);
        try
        {
            // 关键：实例服务必须和管理器的生命周期**解耦**。
            // 不再用管道抓 stdout —— 管道读端在管理器退出/崩溃时关闭，node 下一次写日志
            // 就是 EPIPE 直接退出（实测「管理器崩了实例跟着崩」）。改成生成一个 run.cmd，
            // 把输出重定向进日志文件，再用 cmd 启动它：重定向写在 .cmd 里，
            // 绕开「.NET 传参给 cmd 时的引号转义」这个坑。
            var safeName = string.Join("_", inst.Id.Split(Path.GetInvalidFileNameChars()));
            var runCmd = Path.Combine(LogDir, safeName + ".run.cmd");
            var sb = new StringBuilder();
            sb.AppendLine("@echo off");
            sb.AppendLine("chcp 65001>nul");
            if (inst.Entry.EndsWith(".ts", StringComparison.OrdinalIgnoreCase))
                sb.Append("cd /d ").Append('"').Append(Path.Combine(inst.Dir ?? "", "app")).Append('"').AppendLine();
            sb.Append('"').Append(inst.NodeExe).Append('"').Append(' ');
            var isSource = inst.Entry.EndsWith(".ts", StringComparison.OrdinalIgnoreCase);
            if (isSource) sb.Append("--import tsx/esm ");
            sb.Append('"').Append(inst.Entry).Append('"');
            sb.Append(" web --no-open --port ").Append(inst.Port);
            foreach (var addr in LanAddresses())
                sb.Append(" --trusted-host ").Append(addr).Append(':').Append(BridgePort);
            sb.Append(" >> ").Append('"').Append(log).Append('"').Append(" 2>&1").AppendLine();
            File.WriteAllText(runCmd, sb.ToString(), new UTF8Encoding(false));

            var psi = new ProcessStartInfo("cmd.exe")
            {
                UseShellExecute = false,          // 不重定向任何流：node 的 stdout 是文件而非我们的管道
                CreateNoWindow = true,
                WorkingDirectory = isSource
                    ? (Path.Combine(inst.Dir ?? "", "app"))
                    : (Path.GetDirectoryName(inst.Entry) ?? Environment.CurrentDirectory),
            };
            psi.Arguments = "/c \"" + runCmd + "\"";
            psi.Environment["DSH_HOME"] = inst.Home;

            AppendRaw(log, "[dsh-manager] 启动 " + inst.NodeExe + " " + inst.Entry
                           + " web --no-open --port " + inst.Port);
            var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
            proc.Exited += (_, _) =>
            {
                AppendRaw(log, "[dsh-manager] 启动器已退出（code " + SafeExitCode(proc) + "）");
                lock (Gate) Started.Remove(inst.Id);
            };
            if (!proc.Start())
            {
                message = "进程没有启动起来";
                return false;
            }
            lock (Gate) Started[inst.Id] = new Running { Process = proc };

            // 等端口起来（最多 60 秒；首次启动要跑 TS 入口，慢一点的机器 20 秒不够）
            for (var i = 0; i < 120; i++)
            {
                Thread.Sleep(500);
                DshDiscovery.InvalidateListeners();
                DshDiscovery.Probe(inst);
                if (inst.Running) break;
                if (proc.HasExited) break;
            }
            if (!inst.Running)
            {
                // 进程还活着但端口没起来：多半是还在初始化，不要吓用户说"失败"
                if (!proc.HasExited)
                {
                    message = "服务进程已启动，但 60 秒内端口还没监听（首次启动可能较慢），稍后点刷新；日志：" + log;
                    return false;
                }
                message = "服务进程已退出（code " + SafeExitCode(proc) + "），详见日志：" + log;
                return false;
            }
            message = "服务已就绪（PID " + (inst.Pid > 0 ? inst.Pid.ToString() : proc.Id.ToString())
                      + "，端口 " + inst.Port + "）";
            return true;
        }
        catch (Exception ex)
        {
            message = "启动失败：" + ex.Message;
            return false;
        }
    }

    public static bool Stop(DshInstance inst, out string message)
    {
        message = "";
        DshDiscovery.InvalidateListeners();
        var pid = inst.Pid;
        if (pid <= 0) DshDiscovery.Probe(inst);
        pid = inst.Pid;
        if (pid <= 0)
        {
            message = "没找到监听 " + inst.Port + " 的进程（可能已经停了）";
            DshDiscovery.Probe(inst);
            return false;
        }
        try
        {
            var psi = new ProcessStartInfo("taskkill", "/PID " + pid + " /T /F")
            {
                CreateNoWindow = true, UseShellExecute = false,
                RedirectStandardOutput = true, RedirectStandardError = true,
            };
            using var p = Process.Start(psi);
            p.WaitForExit(8000);
            for (var i = 0; i < 20; i++)
            {
                Thread.Sleep(300);
                DshDiscovery.InvalidateListeners();
                DshDiscovery.Probe(inst);
                if (!inst.Running) break;
            }
            message = inst.Running ? "已发送结束信号，但端口仍在监听" : "服务已停止（PID " + pid + "）";
            return !inst.Running;
        }
        catch (Exception ex)
        {
            message = "停止失败：" + ex.Message;
            return false;
        }
    }

    /// <summary>
    /// 打开窗口 = 管理器自己的内置会话窗口（DshWebWindow，WebView2 装在管理器进程里）。
    /// 端口由管理器下发，认证 cookie 自己签发，不依赖任何外部启动器。
    /// </summary>
    public static bool OpenWindow(DshInstance inst, out string message)
    {
        return DshWebWindow.OpenOrFocus(inst, out message);
    }

    public static string LogPathFor(DshInstance inst)
    {
        Directory.CreateDirectory(LogDir);
        var safe = string.Join("_", inst.Id.Split(Path.GetInvalidFileNameChars()));
        return Path.Combine(LogDir, safe + ".log");
    }

    /// <summary>
    /// 从实例日志里找**最后一次启动**打印的 token（只认最后一条 "dsh web: http://…?token=…"）。
    /// 之前是按「最后 120 行里最后一个匹配」取的，实例重启后可能拿到上一轮的旧 token。
    /// </summary>
    public static string FindStartupToken(DshInstance inst)
    {
        try
        {
            var path = LogPathFor(inst);
            if (!File.Exists(path)) return null;
            using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            using var reader = new StreamReader(fs, Encoding.UTF8);
            var text = reader.ReadToEnd();
            var ms = System.Text.RegularExpressions.Regex.Matches(
                text, @"dsh web:\s*(http://127\.0\.0\.1:\d+/\?token=([A-Za-z0-9_\-\.]+))");
            if (ms.Count == 0) return null;
            return ms[ms.Count - 1].Groups[2].Value;
        }
        catch { return null; }
    }

    /// <summary>当场请求一次带 token 的地址，返回可读的校验结论（200 / 401 / 连不上）。</summary>
    public static string ProbeTokenUrl(string url)
    {
        try
        {
            using var handler = new System.Net.Http.HttpClientHandler
            {
                AllowAutoRedirect = true,
                UseCookies = true,
                CookieContainer = new System.Net.CookieContainer(),
            };
            using var http = new System.Net.Http.HttpClient(handler) { Timeout = TimeSpan.FromSeconds(8) };
            var resp = http.GetAsync(url).GetAwaiter().GetResult();
            var code = (int)resp.StatusCode;
            if (code == 200) return "可打开（200）";
            if (code == 401 || code == 403) return "打不开（" + code + "）—— token 已失效，重启服务后再看";
            return code + "（跟着重定向后的状态码）";
        }
        catch (Exception ex) { return "连不上：" + ex.Message; }
    }

    /// <summary>往实例日志里写一段备注（管理器自己产生的内容，例如 Token 信息）。</summary>
    public static void AppendNote(DshInstance inst, string text)
    {
        try
        {
            var path = LogPathFor(inst);
            var stamp = DateTime.Now.ToString("HH:mm:ss");
            var block = string.Join("\n",
                (text ?? "").TrimEnd().Split('\n').Select(l => stamp + "     note | " + l));
            File.AppendAllText(path, block + Environment.NewLine, new UTF8Encoding(false));
        }
        catch { }
    }

    public static string Tail(DshInstance inst, int lines)
    {
        var path = LogPathFor(inst);
        if (!File.Exists(path)) return "";
        try
        {
            using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            using var reader = new StreamReader(fs, Encoding.UTF8);
            var all = reader.ReadToEnd().Split('\n');
            return string.Join("\n", all.Skip(Math.Max(0, all.Length - lines)).Take(lines)).TrimEnd();
        }
        catch { return ""; }
    }

    public static void OpenFolder(string path)
    {
        try
        {
            if (Directory.Exists(path)) Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
            else if (File.Exists(path))
                Process.Start(new ProcessStartInfo("explorer.exe", "/select,\"" + path + "\"") { UseShellExecute = true });
        }
        catch { }
    }

    private static int SafeExitCode(Process p)
    {
        try { return p.ExitCode; } catch { return -1; }
    }

    /// <summary>手机端桥的端口（和 dsh-mobile-bridge 的默认值一致，可用 DSH_BRIDGE_PORT 覆盖）。</summary>
    private static int BridgePort =>
        int.TryParse(Environment.GetEnvironmentVariable("DSH_BRIDGE_PORT"), out var p) && p > 0 ? p : 8099;

    /// <summary>本机的局域网 IPv4（手机通过这些地址 + 桥端口访问这台机器）。</summary>
    private static IEnumerable<string> LanAddresses()
    {
        System.Net.NetworkInformation.NetworkInterface[] nics;
        try { nics = System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces(); }
        catch { yield break; }
        foreach (var nic in nics)
        {
            if (nic.OperationalStatus != System.Net.NetworkInformation.OperationalStatus.Up) continue;
            System.Net.NetworkInformation.UnicastIPAddressInformationCollection addrs;
            try { addrs = nic.GetIPProperties().UnicastAddresses; }
            catch { continue; }
            foreach (var a in addrs)
            {
                var ip = a.Address;
                if (ip.AddressFamily != System.Net.Sockets.AddressFamily.InterNetwork) continue;
                if (System.Net.IPAddress.IsLoopback(ip)) continue;
                var s = ip.ToString();
                if (s.StartsWith("169.254.")) continue;   // 链路本地地址没用
                yield return s;
            }
        }
    }

    private static void Append(Running running, string log, string line)
    {
        if (line == null) return;
        lock (running.Gate) AppendRaw(log, line);
    }

    private static void AppendRaw(string log, string line)
    {
        try { File.AppendAllText(log, line + Environment.NewLine, Encoding.UTF8); } catch { }
    }

    private static int PickPort(int start)
    {
        if (start < 1024) start = 3080;
        for (var port = start; port < start + 40; port++)
        {
            var l = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, port);
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
}
