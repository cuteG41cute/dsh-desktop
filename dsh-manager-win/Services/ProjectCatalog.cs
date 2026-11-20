using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace DshManager.Services;

/// <summary>一台实例的项目目录快照（给「项目与迁移」列表用）。</summary>
public sealed record InstanceProject(
    string Id,
    string Path,
    string Title,
    int Sessions,
    long SizeBytes,
    DateTime? LastActivity,
    string BackupState,      // none / backup / outdated
    DateTime? LastBackupAt,
    string BackupLocation,   // local / webdav / ""
    bool HasHandoff);

/// <summary>一条备份记录（本地或 WebDAV）。</summary>
public sealed record BackupRecord(
    string ProjectId,
    string ProjectTitle,
    string ProjectPath,
    string Kind,             // local / webdav
    string File,
    string DeviceShort,
    DateTime CreatedAt,
    long SizeBytes,
    string Sha256,
    string Status);          // ok / failed

public static class ProjectCatalog
{
    public static string ManagerDataDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "dsh-manager");

    public static string BackupsFile => Path.Combine(ManagerDataDir, "backups.json");

    /// <summary>实例的 DSH 数据根：优先 &lt;Dir&gt;/dsh-home，否则默认 ~/.dsh。</summary>
    public static string HomeFor(RegistryEntry instance)
    {
        var perInstance = Path.Combine(instance.Dir ?? "", "dsh-home");
        if (!string.IsNullOrEmpty(instance.Dir) && Directory.Exists(perInstance)) return perInstance;
        var envHome = Environment.GetEnvironmentVariable("DSH_HOME");
        if (!string.IsNullOrEmpty(envHome)) return envHome;
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".dsh");
    }

    public static List<InstanceProject> ListProjects(RegistryEntry instance, bool measureSize = true)
    {
        var list = new List<InstanceProject>();
        var home = HomeFor(instance);
        var wsFile = Path.Combine(home, "storages", "workspace.json");
        if (!File.Exists(wsFile)) return list;

        var backups = LoadBackups();

        JsonObject? workspaces = null;
        try
        {
            var wsText = File.ReadAllText(wsFile);
            if (wsText.Length > 0 && wsText[0] == '\uFEFF') wsText = wsText.Substring(1);
            workspaces = JsonNode.Parse(wsText)?["tables"]?["workspaces"]?.AsObject();
        }
        catch { }
        if (workspaces == null) return list;

        foreach (var kv in workspaces)
        {
            var node = kv.Value;
            var path = node?["path"]?.GetValue<string>() ?? "";
            var title = node?["title"]?.GetValue<string>() ?? Path.GetFileName(path);
            var sessionIds = node?["sessionIds"]?.AsArray()?.Select(x => x?.GetValue<string>() ?? "").Where(s => s.Length > 0).ToList()
                             ?? new List<string>();

            var sessionDir = Path.Combine(home, "sessions", ProjectMigration.ProjectKey(path));
            var sessions = sessionIds.Count;
            if (Directory.Exists(sessionDir))
            {
                var onDisk = Directory.GetDirectories(sessionDir).Length;
                if (onDisk > sessions) sessions = onDisk;
            }

            var (lastActivity, sizeBytes) = measureSize
                ? Measure(path, sessionDir)
                : MeasureQuick(path, sessionDir);

            var recs = backups.Where(b => b.ProjectPath.Equals(path, StringComparison.OrdinalIgnoreCase)
                                          || b.ProjectId == kv.Key).OrderByDescending(b => b.CreatedAt).ToList();
            var state = "none";
            DateTime? lastAt = null;
            var location = "";
            if (recs.Count > 0)
            {
                lastAt = recs[0].CreatedAt;
                location = recs[0].Kind;
                state = lastActivity.HasValue && lastActivity.Value > lastAt.Value.AddMinutes(1) ? "outdated" : "backup";
            }

            var handoff = Path.Combine(path, ".dsh", "handoff");
            var hasHandoff = Directory.Exists(handoff) &&
                             Directory.GetFiles(handoff, "*.json").Any(f => !Path.GetFileName(f).StartsWith("."));

            list.Add(new InstanceProject(kv.Key, path, title, sessions, sizeBytes, lastActivity, state, lastAt, location, hasHandoff));
        }
        return list.OrderByDescending(p => p.LastActivity ?? DateTime.MinValue).ToList();
    }

    private static readonly string[] SkipDirs =
        { "node_modules", ".git", ".vs", "bin", "obj", "dist", ".dsh-backup", ".tmp" };

    private static bool Skipped(string root, string file)
    {
        var rel = Path.GetRelativePath(root, file);
        foreach (var part in rel.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar))
        {
            foreach (var s in SkipDirs)
                if (part.Equals(s, StringComparison.OrdinalIgnoreCase)) return true;
        }
        return false;
    }

    /// <summary>快速模式：只看目录/会话目录的修改时间，不递归统计体积。</summary>
    private static (DateTime? LastActivity, long SizeBytes) MeasureQuick(string projectPath, string sessionDir)
    {
        DateTime? last = null;
        try
        {
            if (Directory.Exists(projectPath))
            {
                var t = Directory.GetLastWriteTime(projectPath);
                last = t;
            }
            long size = 0;
            if (Directory.Exists(sessionDir))
            {
                foreach (var f in Directory.EnumerateFiles(sessionDir, "*", SearchOption.AllDirectories))
                {
                    var fi = new FileInfo(f);
                    size += fi.Length;
                    var t = fi.LastWriteTime;
                    if (last == null || t > last) last = t;
                }
            }
            return (last, size);
        }
        catch { }
        return (last, 0);
    }

    private static (DateTime? LastActivity, long SizeBytes) Measure(string projectPath, string sessionDir)
    {
        DateTime? last = null;
        long size = 0;
        try
        {
            if (Directory.Exists(projectPath))
            {
                foreach (var f in Directory.EnumerateFiles(projectPath, "*", SearchOption.AllDirectories))
                {
                    if (Skipped(projectPath, f)) continue;
                    try
                    {
                        var fi = new FileInfo(f);
                        size += fi.Length;
                        if (last == null || fi.LastWriteTimeUtc > last) last = fi.LastWriteTimeUtc;
                    }
                    catch { }
                }
            }
            if (Directory.Exists(sessionDir))
            {
                foreach (var f in Directory.EnumerateFiles(sessionDir, "*", SearchOption.AllDirectories))
                {
                    try
                    {
                        var fi = new FileInfo(f);
                        size += fi.Length;
                        if (last == null || fi.LastWriteTimeUtc > last) last = fi.LastWriteTimeUtc;
                    }
                    catch { }
                }
            }
        }
        catch { }
        return (last?.ToLocalTime(), size);
    }

    public sealed record HandoffInfo(string Device, string At, string Title, string Summary, string RecordPath);

    /// <summary>读取项目最近的交接文件（.dsh/handoff/*.json）。</summary>
    public static HandoffInfo ReadHandoff(string projectPath)
    {
        try
        {
            var dir = Path.Combine(projectPath, ".dsh", "handoff");
            if (!Directory.Exists(dir)) return null;
            var file = Directory.GetFiles(dir, "*.json")
                .Where(f => !Path.GetFileName(f).StartsWith("."))
                .OrderByDescending(File.GetLastWriteTimeUtc).FirstOrDefault();
            if (file == null) return null;
            var node = JsonNode.Parse(File.ReadAllText(file));
            if (node == null) return null;
            return new HandoffInfo(
                node["deviceShort"]?.GetValue<string>() ?? node["deviceId"]?.GetValue<string>() ?? "另一台设备",
                node["exportedAt"]?.GetValue<string>() ?? File.GetLastWriteTime(file).ToString("MM-dd HH:mm"),
                node["title"]?.GetValue<string>() ?? "",
                node["summary"]?.GetValue<string>() ?? "",
                node["fullPath"]?.GetValue<string>() ?? Path.GetFileName(file));
        }
        catch { return null; }
    }

    public static List<BackupRecord> LoadBackups()
    {
        try
        {
            if (!File.Exists(BackupsFile)) return new List<BackupRecord>();
            var arr = JsonNode.Parse(File.ReadAllText(BackupsFile))?.AsArray();
            if (arr == null) return new List<BackupRecord>();
            var list = new List<BackupRecord>();
            foreach (var n in arr)
            {
                if (n == null) continue;
                list.Add(new BackupRecord(
                    n["projectId"]?.GetValue<string>() ?? "",
                    n["projectTitle"]?.GetValue<string>() ?? "",
                    n["projectPath"]?.GetValue<string>() ?? "",
                    n["kind"]?.GetValue<string>() ?? "local",
                    n["file"]?.GetValue<string>() ?? "",
                    n["deviceShort"]?.GetValue<string>() ?? "",
                    DateTime.TryParse(n["createdAt"]?.GetValue<string>(), out var at) ? at : DateTime.MinValue,
                    n["sizeBytes"]?.GetValue<long>() ?? 0,
                    n["sha256"]?.GetValue<string>() ?? "",
                    n["status"]?.GetValue<string>() ?? "ok"));
            }
            return list;
        }
        catch { return new List<BackupRecord>(); }
    }

    public static void SaveBackups(IEnumerable<BackupRecord> records)
    {
        Directory.CreateDirectory(ManagerDataDir);
        var arr = new JsonArray();
        foreach (var r in records)
        {
            arr.Add(new JsonObject
            {
                ["projectId"] = r.ProjectId,
                ["projectTitle"] = r.ProjectTitle,
                ["projectPath"] = r.ProjectPath,
                ["kind"] = r.Kind,
                ["file"] = r.File,
                ["deviceShort"] = r.DeviceShort,
                ["createdAt"] = r.CreatedAt.ToString("o"),
                ["sizeBytes"] = r.SizeBytes,
                ["sha256"] = r.Sha256,
                ["status"] = r.Status,
            });
        }
        File.WriteAllText(BackupsFile, arr.ToJsonString(), new UTF8Encoding(false));
    }
}
