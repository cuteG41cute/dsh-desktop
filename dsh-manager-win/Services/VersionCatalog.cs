using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using System.Threading;

namespace DshManager.Services;

/// <summary>
/// 版本候选：dsh 走 npm registry，Node 走 nodejs.org 的 dist 索引（Windows 版要对齐 Linux 的
/// 「dsh 版本 + Node 版本」两套选择器，所以这两个来源都得联网取）。
/// </summary>
public static class VersionCatalog
{
    // 连接超时单独设短（15s）：否则一条挂死的连接会让整个下载干等 10 分钟，
// 界面一直停在「正在克隆官方仓库并构建…」看起来像卡死（VM 实测遇到过）。
    private static readonly HttpClient Http = new HttpClient(ProxyConfig.Configure(new System.Net.Http.SocketsHttpHandler
    {
        ConnectTimeout = TimeSpan.FromSeconds(15),
        PooledConnectionLifetime = TimeSpan.FromMinutes(2),
    }))
    {
        Timeout = TimeSpan.FromMinutes(10),
    };

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
            // npm 在 Windows 上是 npm.cmd（批处理），CreateProcess 不能直接起它，
            // 必须经 cmd.exe /c —— 否则会抛 Win32Exception，异步任务里就成了「点了没反应」。
            var psi = new ProcessStartInfo("cmd.exe")
            {
                RedirectStandardOutput = true, RedirectStandardError = true,
                UseShellExecute = false, CreateNoWindow = true,
            };
            psi.ArgumentList.Add("/c");
            psi.ArgumentList.Add(npm);
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

    /// <summary>官方仓库可用的 git ref（master + 最近的 tag），供源码实例选版本。</summary>
    public static async Task<List<string>> GitRefsAsync(Action<string> log = null)
    {
        var list = new List<string> { "master" };
        try
        {
            using var http = new HttpClient(ProxyConfig.Configure(new System.Net.Http.SocketsHttpHandler()))
        { Timeout = TimeSpan.FromSeconds(15) };
            http.DefaultRequestHeaders.UserAgent.ParseAdd("dsh-manager");
            var json = await http.GetStringAsync(
                "https://api.github.com/repos/deepseek-ai/deepseek-harness/tags?per_page=40");
            foreach (System.Text.RegularExpressions.Match m in
                     System.Text.RegularExpressions.Regex.Matches(json, "\"name\"\\s*:\\s*\"([^\"]+)\""))
            {
                var name = m.Groups[1].Value;
                if (!list.Contains(name)) list.Add(name);
            }
            log?.Invoke("GitHub tag 候选 " + (list.Count - 1) + " 个");
        }
        catch (Exception ex) { log?.Invoke("GitHub tag 列表失败（只用 master）：" + ex.Message); }
        return list;
    }

    /// <summary>npm 上 dsh 的最新版本号（查不到返回空串）。</summary>
    public static async Task<string> LatestDshAsync()
    {
        try
        {
            var list = await DshVersionsAsync();
            // npm view versions 返回的是「按发布时间从旧到新」的数组：
            // 取第一个会拿到 0.0.1-rc.1（最老的），必须取最后一个非 latest 的。
            // 优先取「非 alpha」的最新版（alpha 是预览版，不该把用户的 rc 版判成"旧"）；
            // 只有全仓都是 alpha 时才退回最后一个。
            string fallback = "";
            for (var i = list.Count - 1; i >= 0; i--)
            {
                var v = list[i];
                if (string.IsNullOrWhiteSpace(v) || v == "latest" || v == SystemNode) continue;
                if (string.IsNullOrEmpty(fallback)) fallback = v;
                if (v.IndexOf("-alpha", StringComparison.OrdinalIgnoreCase) < 0) return v;
            }
            return fallback;
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
            else if (Directory.Exists(target))
            {
                // 上次下载/解压没走完：目录在、node.exe 不在。这种“半成品”直接覆盖重装，
                // 免得解压时和旧文件混在一起（只动实例自己的 node/，dsh-home 等用户数据不动）。
                log("实例里的 Node 目录不完整，清理后重新安装：" + target);
                try { Directory.Delete(target, true); } catch (Exception ex) { log("清理旧 Node 目录失败：" + ex.Message); }
            }

            var v = version == "latest" ? await LatestNodeAsync() : version.TrimStart('v');
            if (string.IsNullOrEmpty(v)) return (false, "没解析出 Node 版本号");

            var zip = Path.Combine(Path.GetTempPath(), "dsh-node-" + v + "-win-x64.zip");
            if (!File.Exists(Path.Combine(target, "node.exe")))
            {
                var url = "https://nodejs.org/dist/v" + v + "/node-v" + v + "-win-x64.zip";
                var ok = false;
                for (var attempt = 1; attempt <= 2 && !ok; attempt++)
                {
                    try
                    {
                        log("下载 Node v" + v + "（win-x64）" + (attempt > 1 ? "（重试 " + attempt + "）" : "") + "…");
                        using var resp = await Http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
                        if (!resp.IsSuccessStatusCode)
                        {
                            log("HTTP " + (int)resp.StatusCode + " " + url);
                            if (attempt == 2) return (false, "下载失败：" + (int)resp.StatusCode + " " + url);
                            continue;
                        }
                        var total = resp.Content.Headers.ContentLength ?? 0;
                        await using var fs = File.Create(zip);
                        await using var src = await resp.Content.ReadAsStreamAsync();
                        var buf = new byte[81920];
                        long got = 0, nextReport = 0;
                        using var stall = new CancellationTokenSource();
                        int n;
                        // 卡住检测：30 秒收不到新字节就当这条连接死了（VM 实测会停在 18MB 不动），
                        // 让外层 catch 走重试，而不是干等 HttpClient 的 10 分钟。
                        stall.CancelAfter(TimeSpan.FromSeconds(30));
                        while ((n = await src.ReadAsync(buf, 0, buf.Length, stall.Token)) > 0)
                        {
                            await fs.WriteAsync(buf, 0, n);
                            got += n;
                            stall.CancelAfter(TimeSpan.FromSeconds(30));
                            if (got >= nextReport)
                            {
                                nextReport = got + 8 * 1024 * 1024;
                                log("  已下载 " + (got / 1024 / 1024) + " MB"
                                    + (total > 0 ? " / " + (total / 1024 / 1024) + " MB" : ""));
                            }
                        }
                        ok = true;
                    }
                    catch (Exception ex)
                    {
                        log("下载出错：" + ex.Message);
                        if (attempt == 2) return (false, "下载 Node 失败：" + ex.Message);
                        await Task.Delay(1500);
                    }
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

    /// <summary>nodejs.org 上最新的 Windows x64 Node 版本号（查不到返回空串）。</summary>
    public static async Task<string> LatestNodeAsync()
    {
        try
        {
            var list = await NodeVersionsAsync();
            return list.FirstOrDefault(v => v != SystemNode && v != "latest") ?? "";
        }
        catch { return ""; }
    }
}
