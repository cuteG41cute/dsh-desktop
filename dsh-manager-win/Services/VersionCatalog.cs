using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace DshManager.Services;

/// <summary>
/// 版本候选：dsh 走 npm registry，Node 走 nodejs.org 的 dist 索引（Windows 版要对齐 Linux 的
/// 「dsh 版本 + Node 版本」两套选择器，所以这两个来源都得联网取）。
/// </summary>
public static class VersionCatalog
{
    private static readonly HttpClient Http = new HttpClient { Timeout = TimeSpan.FromSeconds(20) };

    /// <summary>Linux 版里的兜底列表，网络不通时也还能选。</summary>
    public static readonly string[] FallbackDsh =
    {
        "latest", "0.2.1-rc.5", "0.2.1-rc.4", "0.1.5-rc.1", "0.1.4", "0.1.3",
    };

    public static readonly string[] FallbackNode =
    {
        SystemNode, "latest", "26.13.0", "24.9.0", "22.20.0", "20.19.0",
    };

    /// <summary>「用系统 node」这个选项的取值（默认值，保持和现在行为一致）。</summary>
    public const string SystemNode = "system";

    /// <summary>npm 上 @deepseek-ai/dsh 的版本列表（newest 在前，latest 置顶）。</summary>
    public static async Task<List<string>> DshVersionsAsync(Action<string> log = null)
    {
        try
        {
            var npm = InstanceInstaller.FindNpm();
            if (string.IsNullOrEmpty(npm)) return FallbackDsh.ToList();
            var psi = new ProcessStartInfo(npm)
            {
                RedirectStandardOutput = true, RedirectStandardError = true,
                UseShellExecute = false, CreateNoWindow = true,
            };
            psi.ArgumentList.Add("view");
            psi.ArgumentList.Add("@deepseek-ai/dsh");
            psi.ArgumentList.Add("versions");
            psi.ArgumentList.Add("--json");
            psi.ArgumentList.Add("--silent");
            using var p = Process.Start(psi);
            var json = await p.StandardOutput.ReadToEndAsync();
            await p.WaitForExitAsync();
            if (p.ExitCode != 0 || string.IsNullOrWhiteSpace(json)) return FallbackDsh.ToList();
            using var doc = JsonDocument.Parse(json.TrimStart('\uFEFF', ' ', '\n', '\r'));
            var list = new List<string> { "latest" };
            if (doc.RootElement.ValueKind == JsonValueKind.Array)
            {
                foreach (var el in doc.RootElement.EnumerateArray())
                {
                    var v = el.GetString();
                    if (!string.IsNullOrWhiteSpace(v) && v != "latest") list.Add(v);
                }
            }
            return list.Count > 1 ? list : FallbackDsh.ToList();
        }
        catch (Exception ex)
        {
            log?.Invoke("取 dsh 版本列表失败：" + ex.Message + "（用内置列表）");
            return FallbackDsh.ToList();
        }
    }

    /// <summary>npm 上 dsh 的最新版本号（查不到返回空串）。</summary>
    public static async Task<string> LatestDshAsync()
    {
        try
        {
            var list = await DshVersionsAsync();
            return list.FirstOrDefault(v => v != "latest") ?? "";
        }
        catch { return ""; }
    }

    /// <summary>nodejs.org 上能用于 Windows x64 的 Node 版本（newest 在前）。</summary>
    public static async Task<List<string>> NodeVersionsAsync(Action<string> log = null)
    {
        try
        {
            var text = await Http.GetStringAsync("https://nodejs.org/dist/index.json");
            using var doc = JsonDocument.Parse(text);
            var list = new List<string> { SystemNode, "latest" };
            foreach (var el in doc.RootElement.EnumerateArray())
            {
                if (el.TryGetProperty("version", out var ver) &&
                    el.TryGetProperty("files", out var files) &&
                    files.ValueKind == JsonValueKind.Array &&
                    files.EnumerateArray().Any(f => f.GetString() == "win-x64-zip"))
                {
                    var v = ver.GetString();
                    if (!string.IsNullOrWhiteSpace(v))
                        list.Add(v.TrimStart('v'));   // 统一成 26.13.0 这种写法
                }
                if (list.Count > 80) break;
            }
            return list.Count > 2 ? list : FallbackNode.ToList();
        }
        catch (Exception ex)
        {
            log?.Invoke("取 Node 版本列表失败：" + ex.Message + "（用内置列表）");
            return FallbackNode.ToList();
        }
    }

    /// <summary>
    /// 把指定版本的便携 Node 解到 &lt;dir&gt;\node\（成功时 &lt;dir&gt;\node\node.exe 存在）。
    /// 返回 (ok, 说明)。这一步是真下载（约 30MB），所以带进度回调。
    /// </summary>
    public static async Task<(bool Ok, string Message)> InstallPortableNodeAsync(
        string dir, string version, Action<string> log)
    {
        if (string.IsNullOrWhiteSpace(version) || version == SystemNode)
            return (true, "使用系统 Node");
        try
        {
            Directory.CreateDirectory(dir);
            var target = Path.Combine(dir, "node");
            if (File.Exists(Path.Combine(target, "node.exe")))
                log("实例里已经有 Node，跳过下载：" + target);

            var v = version == "latest" ? await LatestNodeAsync() : version.TrimStart('v');
            if (string.IsNullOrEmpty(v)) return (false, "没解析出 Node 版本号");

            var zip = Path.Combine(Path.GetTempPath(), "dsh-node-" + v + "-win-x64.zip");
            if (!File.Exists(Path.Combine(target, "node.exe")))
            {
                log("下载 Node v" + v + "（win-x64）…");
                var url = "https://nodejs.org/dist/v" + v + "/node-v" + v + "-win-x64.zip";
                using (var resp = await Http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead))
                {
                    if (!resp.IsSuccessStatusCode)
                        return (false, "下载失败：" + (int)resp.StatusCode + " " + url);
                    await using var fs = File.Create(zip);
                    await resp.Content.CopyToAsync(fs);
                }
                log("下载完成：" + new FileInfo(zip).Length / (1024 * 1024) + " MB，解压…");
                var staging = Path.Combine(dir, "node-staging");
                if (Directory.Exists(staging)) Directory.Delete(staging, true);
                System.IO.Compression.ZipFile.ExtractToDirectory(zip, staging, true);
                // zip 里是 node-v<ver>-win-x64/ 一层目录，剥掉它
                var inner = Directory.GetDirectories(staging).FirstOrDefault() ?? staging;
                if (Directory.Exists(target)) Directory.Delete(target, true);
                Directory.Move(inner, target);
                try { Directory.Delete(staging, true); } catch { }
                try { File.Delete(zip); } catch { }
            }
            var exe = Path.Combine(target, "node.exe");
            if (!File.Exists(exe)) return (false, "解压后找不到 node.exe：" + exe);
            log("便携 Node 就绪：" + exe);
            return (true, "已安装便携 Node v" + v);
        }
        catch (Exception ex)
        {
            return (false, "便携 Node 安装失败：" + ex.Message);
        }
    }

    private static async Task<string> LatestNodeAsync()
    {
        try
        {
            var list = await NodeVersionsAsync();
            return list.FirstOrDefault(v => v != SystemNode && v != "latest") ?? "";
        }
        catch { return ""; }
    }
}
