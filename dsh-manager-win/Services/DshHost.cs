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
            var psi = new ProcessStartInfo(inst.NodeExe)
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = Path.GetDirectoryName(inst.Entry) ?? Environment.CurrentDirectory,
            };
            psi.ArgumentList.Add(inst.Entry);
            psi.ArgumentList.Add("web");
            psi.ArgumentList.Add("--no-open");
            psi.ArgumentList.Add("--port");
            psi.ArgumentList.Add(inst.Port.ToString());
            psi.Environment["DSH_HOME"] = inst.Home;

            var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
            var running = new Running { Process = proc };
            proc.OutputDataReceived += (_, e) => Append(running, log, e.Data);
            proc.ErrorDataReceived += (_, e) => Append(running, log, e.Data);
            proc.Exited += (_, _) =>
            {
                Append(running, log, "[dsh-manager] 进程已退出（code " + SafeExitCode(proc) + "）");
                lock (Gate) Started.Remove(inst.Id);
            };

            AppendRaw(log, "[dsh-manager] 启动 " + inst.NodeExe + " " + inst.Entry + " web --no-open --port " + inst.Port);
            if (!proc.Start())
            {
                message = "进程没有启动起来";
                return false;
            }
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            lock (Gate) Started[inst.Id] = running;

            // 等端口起来（最多 20 秒）
            for (var i = 0; i < 40; i++)
            {
                Thread.Sleep(500);
                DshDiscovery.Probe(inst);
                if (inst.Running) break;
                if (proc.HasExited) break;
            }
            if (!inst.Running)
            {
                message = "服务没有在 20 秒内就绪，详见日志：" + log;
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
    /// 打开窗口 = 启动**桌面窗口**（DSH Desktop.exe）。
    /// 启动逻辑已经内置（Services/DesktopLauncher.cs），端口由管理器下发，
    /// 不再调用外部 launcher.ps1（那套会自己扫安装、自己挑端口）。
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
