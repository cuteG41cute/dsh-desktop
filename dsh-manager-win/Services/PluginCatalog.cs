using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace DshManager.Services;

public sealed class PluginInfo
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Repo { get; set; } = "";
    public string Subdir { get; set; } = "";
    public string Desc { get; set; } = "";
    public int Stars { get; set; }
    public string Updated { get; set; } = "";
    public bool Installed { get; set; }
    public string InstalledVersion { get; set; } = "";
    public bool InPatch { get; set; }
    public string Status => !Installed ? "未安装" : (InPatch ? "已安装" : "目录在、未登记");
}

/// <summary>
/// 插件目录 = GitHub 上打了 dsh-plugin topic 的仓库（和 Linux 版同一套发现规则）。
/// 安装 = 下载 tarball → 挑包 → 拷进 profile 的 node_modules → 在 cordis.patch.yml 追加一行。
/// </summary>
public static class PluginCatalog
{
    public const string GhUser = "cuteG41cute";
    public const string GhTopic = "dsh-plugin";

    // 少数仓库的包在子目录里、或者包名与仓库名不同（Linux 版 _hints() 的等价物）
    private static readonly Dictionary<string, (string Id, string Subdir)> Hints =
        new(StringComparer.OrdinalIgnoreCase)
        {
            ["cuteG41cute/dsh-mobile"] = ("dsh-netmon", "netmon"),
        };

    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(30) };

    private static string CachePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "dsh-manager", "plugins-cache.json");

    private static string DownloadDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "dsh-manager", "plugin-cache");

    public static string ProfileDir(DshInstance inst) => Path.Combine(inst.Home, "profiles", "web");
    public static string ModulesDir(DshInstance inst) => Path.Combine(ProfileDir(inst), "node_modules");
    public static string PatchPath(DshInstance inst) => Path.Combine(ProfileDir(inst), "cordis.patch.yml");

    private const string Marker = "# ── installed-by: dsh-manager ({0}) ──";

    // ---------------------------------------------------------------- 发现
    public static List<PluginInfo> LoadCached(out string fetched)
    {
        fetched = "";
        try
        {
            if (!File.Exists(CachePath)) return new List<PluginInfo>();
            using var doc = JsonDocument.Parse(File.ReadAllText(CachePath));
            fetched = doc.RootElement.TryGetProperty("fetched", out var f) ? f.GetString() ?? "" : "";
            var list = new List<PluginInfo>();
            if (doc.RootElement.TryGetProperty("items", out var items))
            {
                foreach (var it in items.EnumerateArray())
                {
                    list.Add(new PluginInfo
                    {
                        Id = Get(it, "id"), Name = Get(it, "name"), Repo = Get(it, "repo"),
                        Subdir = Get(it, "subdir"), Desc = Get(it, "desc"),
                        Stars = it.TryGetProperty("stars", out var s) ? s.GetInt32() : 0,
                        Updated = Get(it, "updated"),
                    });
                }
            }
            return list;
        }
        catch { return new List<PluginInfo>(); }
    }

    private static string Get(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) ? (v.GetString() ?? "") : "";

    public static async Task<List<PluginInfo>> RefreshAsync(string user = GhUser, string topic = GhTopic)
    {
        var url = $"https://api.github.com/users/{user}/repos?per_page=100&sort=updated";
        using var req = new HttpRequestMessage(HttpMethod.Get, url);
        req.Headers.TryAddWithoutValidation("User-Agent", "dsh-manager");
        req.Headers.TryAddWithoutValidation("Accept", "application/vnd.github+json");
        using var resp = await Http.SendAsync(req);
        resp.EnsureSuccessStatusCode();
        var text = await resp.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(text);

        var list = new List<PluginInfo>();
        foreach (var repo in doc.RootElement.EnumerateArray())
        {
            var topics = new List<string>();
            if (repo.TryGetProperty("topics", out var tp))
                foreach (var t in tp.EnumerateArray()) topics.Add((t.GetString() ?? "").ToLowerInvariant());
            if (!topics.Contains(topic.ToLowerInvariant())) continue;

            var full = Get(repo, "full_name");
            var name = Get(repo, "name");
            Hints.TryGetValue(full, out var hint);
            list.Add(new PluginInfo
            {
                Id = string.IsNullOrEmpty(hint.Id) ? name : hint.Id,
                Name = string.IsNullOrEmpty(hint.Id) ? name : hint.Id,
                Repo = full,
                Subdir = hint.Subdir ?? "",
                Desc = Get(repo, "description"),
                Stars = repo.TryGetProperty("stargazers_count", out var s) ? s.GetInt32() : 0,
                Updated = Get(repo, "pushed_at"),
            });
        }
        list = list.OrderBy(p => p.Id).ToList();
        SaveCache(list);
        return list;
    }

    private static void SaveCache(List<PluginInfo> list)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(CachePath)!);
            var payload = new
            {
                fetched = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                user = GhUser, topic = GhTopic,
                items = list.Select(p => new
                {
                    p.Id, p.Name, p.Repo, p.Subdir, p.Desc, p.Stars,
                    updated = p.Updated,
                }),
            };
            File.WriteAllText(CachePath, JsonSerializer.Serialize(payload,
                new JsonSerializerOptions { WriteIndented = true }));
        }
        catch { }
    }

    /// <summary>把「已装状态/版本」补到目录上（读 profile 的 node_modules 与 patch 文件）。</summary>
    public static void MarkInstalled(DshInstance inst, IEnumerable<PluginInfo> list)
    {
        var patch = ReadPatch(inst);
        foreach (var p in list)
        {
            var dir = Path.Combine(ModulesDir(inst), p.Id);
            p.Installed = Directory.Exists(dir);
            p.InstalledVersion = p.Installed ? ReadPackageVersion(dir) : "";
            // 只认「我们写的标记」会漏掉用户手写的 `- id: xxx` 行，于是全部显示"未登记"。
            // 两种都算登记过。
            p.InPatch = patch.Contains(string.Format(Marker, p.Id))
                        || Regex.IsMatch(patch,
                            @"(?m)^\s*-\s*id:\s*['""]?" + Regex.Escape(p.Id) + @"['""]?\s*$");
        }
    }

    /// <summary>node_modules 里装了但不在 GitHub 目录里的（本地包），也列出来。</summary>
    public static List<PluginInfo> ExtraInstalled(DshInstance inst, IEnumerable<PluginInfo> known)
    {
        var ids = new HashSet<string>(known.Select(k => k.Id), StringComparer.OrdinalIgnoreCase);
        var outList = new List<PluginInfo>();
        var dir = ModulesDir(inst);
        if (!Directory.Exists(dir)) return outList;
        foreach (var sub in Directory.GetDirectories(dir))
        {
            var name = Path.GetFileName(sub);
            if (!name.StartsWith("dsh-", StringComparison.OrdinalIgnoreCase) || ids.Contains(name)) continue;
            outList.Add(new PluginInfo
            {
                Id = name, Name = name, Repo = "", Desc = "（本地包，不在 GitHub 目录里）",
                Installed = true, InstalledVersion = ReadPackageVersion(sub),
                InPatch = ReadPatch(inst).Contains(string.Format(Marker, name)),
            });
        }
        return outList;
    }

    private static string ReadPackageVersion(string pkgDir)
    {
        try
        {
            var raw = File.ReadAllBytes(Path.Combine(pkgDir, "package.json"));
            using var doc = JsonDocument.Parse(Encoding.UTF8.GetString(raw).TrimStart('\uFEFF'));
            return doc.RootElement.TryGetProperty("version", out var v) ? (v.GetString() ?? "") : "";
        }
        catch { return ""; }
    }

    private static string ReadPatch(DshInstance inst)
    {
        try { return File.Exists(PatchPath(inst)) ? File.ReadAllText(PatchPath(inst)) : ""; }
        catch { return ""; }
    }

    // ---------------------------------------------------------------- 安装 / 卸载
    public static async Task<(bool Ok, string Message)> InstallAsync(DshInstance inst, PluginInfo p,
        Action<string> log)
    {
        if (string.IsNullOrEmpty(p.Repo)) return (false, "这个插件没有 GitHub 仓库，只能本地导入");
        try
        {
            Directory.CreateDirectory(DownloadDir);
            var tar = Path.Combine(DownloadDir, p.Id + "-main.tar.gz");
            if (!File.Exists(tar) || (DateTime.Now - File.GetLastWriteTime(tar)).TotalHours > 1)
            {
                log("下载 " + p.Repo);
                var bytes = await Http.GetByteArrayAsync(
                    $"https://api.github.com/repos/{p.Repo}/tarball/main");
                await File.WriteAllBytesAsync(tar, bytes);
            }
            else log("使用缓存 " + Path.GetFileName(tar));

            var work = Path.Combine(Path.GetTempPath(), "dsh-plugin-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(work);
            ExtractTarGz(tar, work);

            var root = Directory.GetDirectories(work).FirstOrDefault() ?? work;
            var pkgDir = PickPackage(root, p.Id, p.Subdir);
            if (pkgDir == null) return (false, "包里没找到 package.json（仓库结构变了？）");
            log("选中 " + pkgDir.Substring(root.Length).TrimStart('\\') + "（" + ReadPackageVersion(pkgDir) + "）");

            var target = Path.Combine(ModulesDir(inst), p.Id);
            if (Directory.Exists(target)) Directory.Delete(target, true);
            CopyDir(pkgDir, target);
            AppendPatch(inst, p);
            try { Directory.Delete(work, true); } catch { }
            return (true, "已安装 " + p.Id + " " + ReadPackageVersion(target));
        }
        catch (Exception ex)
        {
            return (false, "安装失败：" + ex.Message);
        }
    }

    public static (bool Ok, string Message) Uninstall(DshInstance inst, PluginInfo p)
    {
        var dir = Path.Combine(ModulesDir(inst), p.Id);
        var removedDir = false;
        try
        {
            if (Directory.Exists(dir)) { Directory.Delete(dir, true); removedDir = true; }
        }
        catch (Exception ex) { return (false, "删除目录失败：" + ex.Message); }
        var removedRow = RemovePatch(inst, p.Id);
        if (!removedDir && !removedRow) return (false, p.Id + " 似乎没装过");
        return (true, "已卸载 " + p.Id + (removedRow ? "（已移除 patch 行）" : ""));
    }

    private static void AppendPatch(DshInstance inst, PluginInfo p)
    {
        var path = PatchPath(inst);
        var text = File.Exists(path) ? File.ReadAllText(path) : "";
        if (text.Contains(string.Format(Marker, p.Id))) return;
        text = Regex.Replace(text, @"(?m)^[ \t]*\[\][ \t]*$", "", RegexOptions.None, TimeSpan.FromSeconds(1));
        if (text.Length > 0 && !text.EndsWith("\n")) text += "\n";
        var block = string.Format(Marker, p.Id) + "\n- insert:\n    - id: " + p.Id
                    + "\n      name: '" + p.Id + "'\n";
        File.WriteAllText(path, text + "\n" + block);
    }

    private static bool RemovePatch(DshInstance inst, string id)
    {
        var path = PatchPath(inst);
        if (!File.Exists(path)) return false;
        var lines = File.ReadAllLines(path).ToList();
        var marker = string.Format(Marker, id);
        var start = lines.FindIndex(l => l.Trim() == marker);
        if (start < 0) return false;
        var end = start + 1;
        if (end < lines.Count && lines[end].TrimStart().StartsWith("- insert:"))
        {
            end++;
            while (end < lines.Count && (lines[end].Trim().Length == 0 || lines[end].StartsWith(" ") || lines[end].StartsWith("\t")))
                end++;
        }
        lines.RemoveRange(start, end - start);
        File.WriteAllText(path, string.Join("\n", lines) + "\n");
        return true;
    }

    // ---------------------------------------------------------------- tar/gzip
    private static void ExtractTarGz(string tarPath, string dest)
    {
        using var fs = File.OpenRead(tarPath);
        using var gz = new GZipStream(fs, CompressionMode.Decompress);
        System.Formats.Tar.TarFile.ExtractToDirectory(gz, dest, overwriteFiles: true);
    }

    private static string PickPackage(string root, string wantId, string subdir)
    {
        var wanted = string.IsNullOrEmpty(subdir) ? "" : Path.GetFullPath(Path.Combine(root, subdir));
        string best = null;
        var bestScore = int.MaxValue;
        foreach (var dir in Directory.GetDirectories(root, "*", SearchOption.AllDirectories))
        {
            if (dir.Contains(Path.DirectorySeparatorChar + "node_modules" + Path.DirectorySeparatorChar)) continue;
            var pkg = Path.Combine(dir, "package.json");
            if (!File.Exists(pkg)) continue;
            var score = 100;
            if (!string.IsNullOrEmpty(wanted) && Path.GetFullPath(dir) == wanted) score = 0;
            else
            {
                var json = File.ReadAllText(pkg);
                if (json.Contains("\"dsh\"")) score = 10;
                if (json.Contains("\"name\": \"" + wantId + "\"") || json.Contains("\"name\":\"" + wantId + "\"")) score = 5;
            }
            if (score < bestScore) { bestScore = score; best = dir; }
        }
        return best;
    }

    private static void CopyDir(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (var file in Directory.GetFiles(src))
            File.Copy(file, Path.Combine(dst, Path.GetFileName(file)), true);
        foreach (var dir in Directory.GetDirectories(src))
        {
            var name = Path.GetFileName(dir);
            if (name == "node_modules" || name == ".git") continue;
            CopyDir(dir, Path.Combine(dst, name));
        }
    }
}
