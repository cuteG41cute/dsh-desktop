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

            SeedIsolatedHome(dir, log);
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

    public const string SourceRepo = "https://github.com/deepseek-ai/deepseek-harness.git";
    public const string PnpmVersion = "11.28.5";

    /// <summary>源码实例的入口（repo 里的 CLI，用 tsx 直接跑 TS）。</summary>
    public static string SourceEntry(string dir) =>
        Path.Combine(dir, "app", "apps", "cli", "src", "bin.ts");

    /// <summary>
    /// 从官方仓库克隆一份**全新**实例：git clone → 装 pnpm 到实例目录 → pnpm install → pnpm run build。
    /// 全程只用实例目录里的 portable Node，不碰系统的 npm/pnpm 全局状态。
    /// </summary>
    public static async Task<(bool Ok, string Message)> InstallSourceAsync(
        string dir, string nodeVersion, Action<string> log, int port)
    {
        try
        {
            Directory.CreateDirectory(dir);
            var (nok, nmsg) = await VersionCatalog.InstallPortableNodeAsync(dir, nodeVersion, log);
            if (!nok) return (false, nmsg);
            var node = Path.Combine(dir, "node", "node.exe");
            var npm = Path.Combine(dir, "node", "npm.cmd");
            if (!File.Exists(node)) return (false, "实例里没有 node.exe（请选择具体 Node 版本，源码实例必须自带 Node）");

            var app = Path.Combine(dir, "app");
            if (!Directory.Exists(Path.Combine(app, ".git")))
            {
                if (Directory.Exists(app)) Directory.Delete(app, true);
                log("克隆官方仓库：" + SourceRepo);
                var (cok, cmsg) = await RunAsync("git", new[]
                {
                    "clone", "--depth", "1", SourceRepo, app,
                }, dir, log, TimeSpan.FromMinutes(30));
                if (!cok) return (false, "git clone 失败：" + cmsg);
            }
            else log("仓库已存在，跳过 clone：" + app);

            var tools = Path.Combine(dir, "tools");
            var pnpmCjs = Path.Combine(tools, "node_modules", "pnpm", "bin", "pnpm.cjs");
            if (!File.Exists(pnpmCjs))
            {
                log("在实例目录里装 pnpm " + PnpmVersion + "（不装全局）…");
                var (pok, pmsg) = await RunAsync(npm, new[]
                {
                    "install", "pnpm@" + PnpmVersion, "--prefix", tools,
                    "--no-audit", "--no-fund", "--loglevel=error",
                }, dir, log, TimeSpan.FromMinutes(20), node);
                if (!pok) return (false, "pnpm 安装失败：" + pmsg);
            }
            if (!File.Exists(pnpmCjs)) return (false, "pnpm 没装上：" + pnpmCjs);

            var store = Path.Combine(dir, "pnpm-store");
            log("pnpm install（store 也在实例目录里）…");
            var (iok, imsg) = await RunAsync(node, new[]
            {
                pnpmCjs, "install", "--config.store-dir=" + store,
            }, app, log, TimeSpan.FromMinutes(60), node);
            if (!iok) return (false, "pnpm install 失败：" + imsg);

            log("pnpm run build（这一步最慢，可能要十几分钟）…");
            var (bok, bmsg) = await RunAsync(node, new[]
            {
                pnpmCjs, "run", "build",
            }, app, log, TimeSpan.FromMinutes(90), node);
            if (!bok) return (false, "构建失败：" + bmsg);

            var entry = SourceEntry(dir);
            if (!File.Exists(entry)) return (false, "构建完成但找不到 CLI 入口：" + entry);
            log("完成：" + entry);

            var ver = ReadVersion(Path.Combine(app, "package.json"));
            InstanceRegistry.Add(new RegistryEntry
            {
                Id = "own@" + DshDiscovery.StableHash(dir),
                Label = new DirectoryInfo(dir).Name,
                Dir = dir,
                Port = port,
                DshVersion = ver,
                NodeVersion = nodeVersion ?? "",
                CreatedAt = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
            });
            SeedIsolatedHome(dir, log);
            return (true, "已创建源码实例 " + new DirectoryInfo(dir).Name + "（仓库版本 " + ver + "）");
        }
        catch (Exception ex)
        {
            return (false, "源码实例安装失败：" + ex.Message);
        }
    }

    /// <summary>跑一个子进程，把输出逐行喂给 log。nodeDir 非空时前置到 PATH（用实例自带 node）。</summary>
    private static async Task<(bool Ok, string Message)> RunAsync(
        string exe, string[] args, string workDir, Action<string> log,
        TimeSpan timeout, string nodeDir = null)
    {
        try
        {
            var psi = new ProcessStartInfo(exe)
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = new System.Text.UTF8Encoding(false),
                StandardErrorEncoding = new System.Text.UTF8Encoding(false),
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = workDir,
            };
            foreach (var a in args) psi.ArgumentList.Add(a);
            if (!string.IsNullOrEmpty(nodeDir))
            {
                psi.Environment["PATH"] = Path.GetDirectoryName(nodeDir) + ";" + Path.GetDirectoryName(exe)
                                          + ";" + (Environment.GetEnvironmentVariable("PATH") ?? "");
                psi.Environment["COREPACK_ENABLE_STRICT"] = "0";
                psi.Environment["PNPM_HOME"] = Path.Combine(Path.GetDirectoryName(Path.GetDirectoryName(nodeDir)) ?? "", "tools");
            }
            var tail = new StringBuilder();
            var proc = new Process { StartInfo = psi };
            proc.OutputDataReceived += (_, e) => { if (e.Data != null) { log(e.Data); lock (tail) { tail.AppendLine(e.Data); } } };
            proc.ErrorDataReceived += (_, e) => { if (e.Data != null) { log(e.Data); lock (tail) { tail.AppendLine(e.Data); } } };
            if (!proc.Start()) return (false, "进程没起来：" + exe);
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            using var cts = new System.Threading.CancellationTokenSource(timeout);
            try { await proc.WaitForExitAsync(cts.Token); }
            catch (OperationCanceledException)
            {
                try { proc.Kill(true); } catch { }
                return (false, "超时（" + (int)timeout.TotalMinutes + " 分钟）");
            }
            if (proc.ExitCode != 0) return (false, "退出码 " + proc.ExitCode + "：" + LastLines(tail.ToString(), 3));
            return (true, "ok");
        }
        catch (Exception ex)
        {
            return (false, ex.Message);
        }
    }

    /// <summary>
    /// 给新实例建**全新的** DSH_HOME：只创建空目录，不从全局家目录搬任何东西。
    /// 新实例 = 干净环境：没有别人的工作区/会话/插件/设置，
    /// 首次启动由 dsh 自己生成默认配置（模型凭据也在该实例里单独配）。
    /// </summary>
    private static void SeedIsolatedHome(string dir, Action<string> log)
    {
        try
        {
            var home = Path.Combine(dir, "dsh-home");
            Directory.CreateDirectory(home);
            log("已建全新数据目录：" + home + "（不继承任何会话/工作区/插件/设置）");
        }
        catch (Exception ex)
        {
            log("创建数据目录失败（将沿用全局 .dsh）：" + ex.Message);
        }
    }

    private static void CopyDir(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (var f in Directory.GetFiles(src))
            File.Copy(f, Path.Combine(dst, Path.GetFileName(f)), true);
        foreach (var d in Directory.GetDirectories(src))
            CopyDir(d, Path.Combine(dst, Path.GetFileName(d)));
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
