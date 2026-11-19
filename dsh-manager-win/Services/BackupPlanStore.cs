using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace DshManager.Services;

/// <summary>自动备份计划（按实例保存）。</summary>
public sealed class BackupPlan
{
    public bool Enabled { get; set; }
    public string Frequency { get; set; } = "daily";   // daily / weekly / hours
    public string Time { get; set; } = "03:00";        // daily / weekly
    public int Hours { get; set; } = 6;                // hours
    public string Scope { get; set; } = "all";         // all / selected
    public List<string> ProjectIds { get; set; } = new();
    public string Directory { get; set; } = "";
    public int RetentionCount { get; set; } = 1;
    public int RetentionDays { get; set; }
    public bool IncludeSessions { get; set; } = true;
    public bool IncludeProjectFiles { get; set; } = true;
    public bool IncludeAttachments { get; set; } = true;
    public DateTime? LastRunAt { get; set; }
    public DateTime? NextRunAt { get; set; }

    public DateTime ComputeNext(DateTime now)
    {
        if (Frequency == "hours")
        {
            var next = now.AddHours(Math.Max(1, Hours));
            return new DateTime(next.Year, next.Month, next.Day, next.Hour, 0, 0);
        }
        var parts = (Time ?? "03:00").Split(':');
        var hh = parts.Length > 0 && int.TryParse(parts[0], out var h) ? h : 3;
        var mm = parts.Length > 1 && int.TryParse(parts[1], out var m) ? m : 0;
        var candidate = new DateTime(now.Year, now.Month, now.Day, hh, mm, 0);
        if (Frequency == "weekly")
        {
            while (candidate.DayOfWeek != DayOfWeek.Monday) candidate = candidate.AddDays(1);
        }
        if (candidate <= now) candidate = candidate.AddDays(Frequency == "weekly" ? 7 : 1);
        return candidate;
    }
}

public static class BackupPlanStore
{
    private static string FilePath => Path.Combine(ProjectCatalog.ManagerDataDir, "backup-plan.json");

    public static BackupPlan Load(string instanceId)
    {
        try
        {
            if (!File.Exists(FilePath)) return new BackupPlan();
            var root = JsonNode.Parse(File.ReadAllText(FilePath))?.AsObject();
            var node = root?[instanceId];
            if (node == null) return new BackupPlan();
            var plan = new BackupPlan
            {
                Enabled = node["enabled"]?.GetValue<bool>() ?? false,
                Frequency = node["frequency"]?.GetValue<string>() ?? "daily",
                Time = node["time"]?.GetValue<string>() ?? "03:00",
                Hours = node["hours"]?.GetValue<int>() ?? 6,
                Scope = node["scope"]?.GetValue<string>() ?? "all",
                Directory = node["directory"]?.GetValue<string>() ?? "",
                RetentionCount = node["retentionCount"]?.GetValue<int>() ?? 1,
                RetentionDays = node["retentionDays"]?.GetValue<int>() ?? 0,
                IncludeSessions = node["includeSessions"]?.GetValue<bool>() ?? true,
                IncludeProjectFiles = node["includeProjectFiles"]?.GetValue<bool>() ?? true,
                IncludeAttachments = node["includeAttachments"]?.GetValue<bool>() ?? true,
            };
            foreach (var id in node["projectIds"]?.AsArray() ?? new JsonArray())
                if (id != null) plan.ProjectIds.Add(id.GetValue<string>());
            if (DateTime.TryParse(node["lastRunAt"]?.GetValue<string>(), out var last)) plan.LastRunAt = last;
            if (DateTime.TryParse(node["nextRunAt"]?.GetValue<string>(), out var next)) plan.NextRunAt = next;
            return plan;
        }
        catch { return new BackupPlan(); }
    }

    public static void Save(string instanceId, BackupPlan plan)
    {
        Directory.CreateDirectory(ProjectCatalog.ManagerDataDir);
        JsonObject root;
        try
        {
            root = File.Exists(FilePath)
                ? JsonNode.Parse(File.ReadAllText(FilePath))?.AsObject() ?? new JsonObject()
                : new JsonObject();
        }
        catch { root = new JsonObject(); }

        var ids = new JsonArray();
        foreach (var id in plan.ProjectIds) ids.Add(id);
        root[instanceId] = new JsonObject
        {
            ["enabled"] = plan.Enabled,
            ["frequency"] = plan.Frequency,
            ["time"] = plan.Time,
            ["hours"] = plan.Hours,
            ["scope"] = plan.Scope,
            ["projectIds"] = ids,
            ["directory"] = plan.Directory,
            ["retentionCount"] = plan.RetentionCount,
            ["retentionDays"] = plan.RetentionDays,
            ["includeSessions"] = plan.IncludeSessions,
            ["includeProjectFiles"] = plan.IncludeProjectFiles,
            ["includeAttachments"] = plan.IncludeAttachments,
            ["lastRunAt"] = plan.LastRunAt?.ToString("o") ?? "",
            ["nextRunAt"] = plan.NextRunAt?.ToString("o") ?? "",
        };
        File.WriteAllText(FilePath, root.ToJsonString(), new UTF8Encoding(false));
    }

    /// <summary>按保留策略清理旧包（保留份数 / 天数）。</summary>
    public static void ApplyRetention(string projectDir, string projectTitle, int keepCount, int keepDays)
    {
        try
        {
            if (!Directory.Exists(projectDir)) return;
            var files = Directory.GetFiles(projectDir, "*.dshproj")
                .Select(f => new FileInfo(f)).OrderByDescending(f => f.LastWriteTimeUtc).ToList();
            var keep = Math.Max(1, keepCount);
            for (var i = 0; i < files.Count; i++)
            {
                var expiredByCount = i >= keep;
                var expiredByDays = keepDays > 0 && files[i].LastWriteTimeUtc < DateTime.UtcNow.AddDays(-keepDays);
                if (expiredByCount || expiredByDays) { try { files[i].Delete(); } catch { } }
            }
        }
        catch { }
    }
}

/// <summary>无 UI 依赖的备份执行器（定时器与按钮共用）。</summary>
public static class BackupRunner
{
    public sealed record Result(int Ok, int Failed, List<string> Messages);

    public static Result Run(RegistryEntry instance, BackupPlan plan, IReadOnlyCollection<InstanceProject> projects,
        Action<string> log = null)
    {
        var dir = string.IsNullOrWhiteSpace(plan.Directory)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "dsh-backup")
            : plan.Directory;
        Directory.CreateDirectory(dir);
        var records = ProjectCatalog.LoadBackups();
        int ok = 0, failed = 0;
        var messages = new List<string>();
        foreach (var p in projects)
        {
            var targetDir = plan.RetentionCount > 1 ? Path.Combine(dir, SafeName(p.Title)) : dir;
            Directory.CreateDirectory(targetDir);
            var file = plan.RetentionCount > 1
                ? Path.Combine(targetDir, SafeName(p.Title) + "-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".dshproj")
                : Path.Combine(targetDir, SafeName(p.Title) + ".dshproj");
            var (success, msg) = ProjectMigration.Export(
                new ProjectMigration.ProjectInfo(p.Id, p.Path, p.Title, p.Sessions),
                file, plan.IncludeProjectFiles, log, ProjectCatalog.HomeFor(instance),
                default, plan.IncludeAttachments);
            if (success)
            {
                ok++;
                records.RemoveAll(r => r.ProjectPath.Equals(p.Path, StringComparison.OrdinalIgnoreCase)
                                       && r.Kind == "local");
                records.Add(new BackupRecord(p.Id, p.Title, p.Path, "local", file,
                    "win-" + Environment.MachineName.ToLowerInvariant(), DateTime.Now,
                    new FileInfo(file).Length, "", "ok"));
                if (plan.RetentionCount > 1)
                    BackupPlanStore.ApplyRetention(targetDir, p.Title, plan.RetentionCount, plan.RetentionDays);
            }
            else
            {
                failed++;
                messages.Add(p.Title + "：" + msg);
            }
        }
        ProjectCatalog.SaveBackups(records);
        return new Result(ok, failed, messages);
    }

    public static string SafeName(string name)
    {
        foreach (var ch in Path.GetInvalidFileNameChars()) name = name.Replace(ch, '_');
        return name;
    }
}
