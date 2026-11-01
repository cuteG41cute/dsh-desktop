using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace DshManager.Services;

/// <summary>
/// 新建实例 = 在指定目录里装一份 @deepseek-ai/dsh（用系统 node/npm），然后登记到 instances.json。
/// Windows 上没有 Linux 那套「自带 node 的便携实例」约定，这里直接用系统 node：
/// 更简单，也跟本机现有安装一致（现在跑的就是 C:\Program Files\nodejs\node.exe）。
/// </summary>
public static class InstanceInstaller
{
    public static string FindNpm()
    {
        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var part in path.Split(';'))
        {
            if (string.IsNullOrWhiteSpace(part)) continue;
            var dir = part.Trim();
            var cmd = Path.Combine(dir, "npm.cmd");
            if (File.Exists(cmd)) return cmd;
        }
        return "";
    }

    public static string FindNode()
    {
        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var part in path.Split(';'))
        {
            if (string.IsNullOrWhiteSpace(part)) continue;
            var exe = Path.Combine(part.Trim(), "node.exe");
            if (File.Exists(exe)) return exe;
        }
        return "";
    }

    /// <summary>
    /// 在 dir 里安装 dsh。version 为空或 "latest" 就装最新版。
    /// 返回 (ok, 说明)。log 会收到 npm 的实时输出（用来显示在对话框里）。
    /// </summary>
    public static async Task<(bool Ok, string Message)> InstallAsync(
        string dir, string version, Action<string> log, int port,
        string nodeVersion = VersionCatalog.SystemNode)
    {
        var npm = FindNpm();
        if (string.IsNullOrEmpty(npm)) return (false, "PATH 上找不到 npm.cmd（先装 Node.js）");
        if (string.IsNullOrWhiteSpace(dir)) return (false, "没有指定安装目录");
        var spec = string.IsNullOrWhiteSpace(version) || version == "latest"
            ? "@deepseek-ai/dsh@latest"
            : "@deepseek-ai/dsh@" + version.Trim();

        try
        {
            Directory.CreateDirectory(dir);
            // 便携 Node：选了具体版本就真下载到 <dir>\node\（对齐 Linux 的实例自带 node）
            var (nok, nmsg) = await VersionCatalog.InstallPortableNodeAsync(dir, nodeVersion, log);
            if (!nok) return (false, nmsg);
            if (!string.IsNullOrEmpty(nodeVersion) && nodeVersion != VersionCatalog.SystemNode)
                log(nmsg);
            log("目录：" + dir);
            log("命令：npm install " + spec + " --prefix …");
            var psi = new ProcessStartInfo(npm)
            {
                RedirectStandardOutput = true, RedirectStandardError = true,
                UseShellExecute = false, CreateNoWindow = true,
                WorkingDirectory = dir,
            };
            psi.ArgumentList.Add("install");
            psi.ArgumentList.Add(spec);
            psi.ArgumentList.Add("--prefix");
            psi.ArgumentList.Add(dir);
            psi.ArgumentList.Add("--no-audit");
            psi.ArgumentList.Add("--no-fund");
            psi.ArgumentList.Add("--loglevel=error");
            // 实例自带了便携 Node 时，npm 也用它的（PATH 前置，npm.cmd 会调 node）
            var instNodeDir = Path.Combine(dir, "node");
            if (File.Exists(Path.Combine(instNodeDir, "node.exe")))
                psi.Environment["PATH"] = instNodeDir + ";" +
                    (Environment.GetEnvironmentVariable("PATH") ?? "");

            var proc = new Process { StartInfo = psi };
            var buffer = new StringBuilder();
            proc.OutputDataReceived += (_, e) => { if (e.Data != null) { lock (buffer) buffer.AppendLine(e.Data); log(e.Data); } };
            proc.ErrorDataReceived += (_, e) => { if (e.Data != null) { lock (buffer) buffer.AppendLine(e.Data); log(e.Data); } };
            if (!proc.Start()) return (false, "npm 没有启动起来");
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();

            using var cts = new System.Threading.CancellationTokenSource(TimeSpan.FromMinutes(10));
            try
            {
                await proc.WaitForExitAsync(cts.Token);
            }
            catch (OperationCanceledException)
            {
                try { proc.Kill(true); } catch { }
                return (false, "安装超过 10 分钟，已中止");
            }
            if (proc.ExitCode != 0)
                return (false, "npm 退出码 " + proc.ExitCode + "：" + LastLines(buffer.ToString(), 3));

            var entry = Path.Combine(dir, "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js");
            if (!File.Exists(entry)) return (false, "装完了但找不到 bin.js（目录结构变了？）");
            log("完成：" + entry);

            var versionText = ReadVersion(Path.Combine(dir, "node_modules", "@deepseek-ai", "dsh", "package.json"));
            var id = "own@" + DshDiscovery.StableHash(dir);
            InstanceRegistry.Add(new RegistryEntry
            {
                Id = id,
                Label = new DirectoryInfo(dir).Name,
                Dir = dir,
                Port = port,
                DshVersion = versionText,
                NodeVersion = nodeVersion ?? "",
                CreatedAt = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
            });
            return (true, "已创建实例 " + new DirectoryInfo(dir).Name + "（dsh " + versionText + "）");
        }
        catch (Exception ex)
        {
            return (false, "安装失败：" + ex.Message);
        }
    }

    private static string LastLines(string text, int n)
    {
        var lines = text.Split('\n').Where(l => l.Trim().Length > 0).ToList();
        return string.Join(" / ", lines.Skip(Math.Max(0, lines.Count - n)));
    }

    private static string ReadVersion(string pkgPath)
    {
        try
        {
            var raw = File.ReadAllText(pkgPath).TrimStart('\uFEFF');
            using var doc = System.Text.Json.JsonDocument.Parse(raw);
            return doc.RootElement.TryGetProperty("version", out var v) ? (v.GetString() ?? "") : "";
        }
        catch { return ""; }
    }
}
