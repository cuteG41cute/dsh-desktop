using System;
using System.Collections.Generic;
using System.Formats.Tar;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;

namespace DshManager.Services;

/// <summary>
/// 项目迁移：把 DSH 里的一个「工作空间」（项目目录 + 会话记录 + 注册表条目）
/// 打包成一个 .dshproj（tar.gz），可在另一台机器的管理器里导入。
/// </summary>
public static class ProjectMigration
{
    public sealed record ProjectInfo(string Id, string Path, string Title, int SessionCount);

    private sealed record Manifest(string Format, string Title, string SourcePath, string CreatedAt, string DshVersion);

    public static string DshHome =>
        string.IsNullOrEmpty(Environment.GetEnvironmentVariable("DSH_HOME"))
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".dsh")
            : Environment.GetEnvironmentVariable("DSH_HOME");

    private static string WorkspaceFile => WorkspaceFileFor(null);
    private static string SessionsRoot => SessionsRootFor(null);

    private static string WorkspaceFileFor(string home) =>
        Path.Combine(home ?? DshHome, "storages", "workspace.json");

    private static string SessionsRootFor(string home) =>
        Path.Combine(home ?? DshHome, "sessions");

    /// <summary>DSH 的 projectKey：分隔符折叠成 '-'，其他不安全字符转 ~XXXX。</summary>
    public static string ProjectKey(string cwd)
    {
        if (string.IsNullOrEmpty(cwd)) throw new ArgumentException("empty path");
        var sb = new StringBuilder();
        var sep = false;
        foreach (var ch in cwd)
        {
            if (ch == '/' || ch == '\\' || ch == ':')
            {
                if (!sep) sb.Append('-');
                sep = true;
            }
            else if (ch != '~' && (char.IsLetterOrDigit(ch) && ch < 128 || ch == '.' || ch == '_' || ch == '-'))
            {
                sb.Append(ch);
                sep = false;
            }
            else
            {
                sb.Append('~').Append(((int)ch).ToString("X4"));
                sep = false;
            }
        }
        var body = sb.ToString().TrimStart('-');
        if (body.Length == 0) body = "root";
        if (body.Length > 251) body = body[..251];
        return "--" + body + "--";
    }

    public static List<ProjectInfo> ListProjects()
    {
        var list = new List<ProjectInfo>();
        try
        {
            if (!File.Exists(WorkspaceFile)) return list;
            var json = JsonNode.Parse(File.ReadAllText(WorkspaceFile));
            var ws = json?["tables"]?["workspaces"]?.AsObject();
            if (ws == null) return list;
            foreach (var kv in ws)
            {
                var node = kv.Value;
                var path = node?["path"]?.GetValue<string>() ?? "";
                var title = node?["title"]?.GetValue<string>() ?? Path.GetFileName(path);
                var ids = node?["sessionIds"]?.AsArray()?.Count ?? 0;
                list.Add(new ProjectInfo(kv.Key, path, title, ids));
            }
        }
        catch { }
        return list.OrderBy(p => p.Title).ToList();
    }

    /// <summary>导出：manifest + 注册表条目 + 会话记录 + （可选）项目文件。</summary>
    public static (bool Ok, string Message) Export(ProjectInfo project, string bundlePath, bool includeFiles,
        Action<string> log = null, string dshHome = null, CancellationToken ct = default)
    {
        var wsFile = WorkspaceFileFor(dshHome);
        var sessionsRoot = SessionsRootFor(dshHome);
        try
        {
            if (!File.Exists(wsFile)) return (false, "找不到 DSH 的 workspace.json：" + wsFile);
            var tmp = bundlePath + ".tmp";
            if (File.Exists(tmp)) File.Delete(tmp);

            var manifest = new Manifest("dsh-project-v1", project.Title, project.Path,
                DateTime.Now.ToString("o"), "dsh");

            using (var fs = File.Create(tmp))
            using (var gz = new GZipStream(fs, CompressionLevel.Optimal, false))
            using (var tar = new TarWriter(gz, TarEntryFormat.Pax, true))
            {
                ct.ThrowIfCancellationRequested();
                AddText(tar, "manifest.json", JsonSerializer.Serialize(manifest,
                    new JsonSerializerOptions { WriteIndented = true }));

                var json = JsonNode.Parse(File.ReadAllText(wsFile));
                var entry = json?["tables"]?["workspaces"]?[project.Id];
                if (entry != null) AddText(tar, "state/workspace-entry.json", entry.ToJsonString());
                var sessionIds = entry?["sessionIds"]?.AsArray()?
                    .Select(x => x?.GetValue<string>() ?? "").Where(s => s.Length > 0)
                    .ToHashSet(StringComparer.OrdinalIgnoreCase) ?? new HashSet<string>();

                // 会话缓存（标题、token 统计、goal）按 sessionId 过滤
                var cacheRoot = Path.Combine(dshHome ?? DshHome, "storages", "session_projcache", "sessions");
                if (Directory.Exists(cacheRoot) && project.SessionCount > 0)
                {
                    foreach (var f in Directory.EnumerateFiles(cacheRoot, "*.json"))
                    {
                        var name = Path.GetFileNameWithoutExtension(f);
                        if (name != null && sessionIds.Contains(name))
                            AddFile(tar, f, "state/projcache/" + Path.GetFileName(f));
                    }
                }

                var key = ProjectKey(project.Path);
                var sessionDir = Path.Combine(sessionsRoot, key);
                log?.Invoke("会话目录：" + sessionDir);
                if (Directory.Exists(sessionDir)) AddDir(tar, sessionDir, "sessions", ct);

                if (includeFiles && Directory.Exists(project.Path))
                {
                    ct.ThrowIfCancellationRequested();
                    log?.Invoke("打包项目文件：" + project.Path);
                    AddDir(tar, project.Path, "project", ct, skip: new[]
                    {
                        "node_modules", ".git", ".dsh-backup", "bin", "obj", "dist", ".vs", ".tmp",
                    });
                }
            }

            if (File.Exists(bundlePath)) File.Delete(bundlePath);
            File.Move(tmp, bundlePath);
            var size = new FileInfo(bundlePath).Length / 1024.0 / 1024.0;
            log?.Invoke($"完成：{Path.GetFileName(bundlePath)}（{size:F1} MB）");
            return (true, $"已导出「{project.Title}」（{size:F1} MB）");
        }
        catch (OperationCanceledException) { return (false, "已取消导出"); }
        catch (Exception ex) { return (false, "导出失败：" + ex.Message); }
    }

    /// <summary>导入：解包到新目录、复制会话、写注册表；需要重启实例后可见。</summary>
    public static (bool Ok, string Message) Import(string bundlePath, string destRoot, Action<string> log = null,
        string dshHome = null)
    {
        var wsFile = WorkspaceFileFor(dshHome);
        var sessionsRoot = SessionsRootFor(dshHome);
        try
        {
            var work = Path.Combine(Path.GetTempPath(), "dshproj-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(work);
            using (var fs = File.OpenRead(bundlePath))
            using (var gz = new GZipStream(fs, CompressionMode.Decompress))
            using (var tar = new TarReader(gz))
            {
                TarEntry e;
                while ((e = tar.GetNextEntry()) != null)
                {
                    var target = Path.GetFullPath(Path.Combine(work, e.Name));
                    if (!target.StartsWith(work, StringComparison.OrdinalIgnoreCase)) continue;
                    if (e.EntryType == TarEntryType.Directory)
                    {
                        Directory.CreateDirectory(target);
                    }
                    else if (e.DataStream != null)
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(target));
                        using var outFs = File.Create(target);
                        e.DataStream.CopyTo(outFs);
                    }
                }
            }

            var manifestPath = Path.Combine(work, "manifest.json");
            if (!File.Exists(manifestPath)) return (false, "包里没有 manifest.json，不是有效的项目包");
            var manifest = JsonSerializer.Deserialize<Manifest>(File.ReadAllText(manifestPath));
            var title = manifest?.Title ?? Path.GetFileNameWithoutExtension(bundlePath);

            // 1) 项目文件
            var srcProject = Path.Combine(work, "project");
            var destProject = Path.Combine(destRoot, title);
            if (Directory.Exists(srcProject))
            {
                if (Directory.Exists(destProject))
                    destProject = destProject + "-" + DateTime.Now.ToString("MMddHHmm");
                Directory.CreateDirectory(destRoot);
                CopyDir(srcProject, destProject);
                log?.Invoke("项目文件 → " + destProject);
            }
            else
            {
                Directory.CreateDirectory(destProject);
            }

            // 2) 会话记录（按新路径重新编码目录名）
            var id = Guid.NewGuid().ToString();
            var newKey = ProjectKey(destProject);
            var srcSessions = Path.Combine(work, "sessions");
            var sessionIds = new List<string>();
            if (Directory.Exists(srcSessions))
            {
                var destSessions = Path.Combine(sessionsRoot, newKey);
                CopyDir(srcSessions, destSessions);
                foreach (var d in Directory.GetDirectories(srcSessions))
                    sessionIds.Add(Path.GetFileName(d));
                log?.Invoke($"会话 {sessionIds.Count} 个 → {destSessions}");
            }

            // 2.5) 会话缓存（标题 / 统计 / goal）
            var srcCache = Path.Combine(work, "state", "projcache");
            if (Directory.Exists(srcCache))
            {
                var destCache = Path.Combine(dshHome ?? DshHome, "storages", "session_projcache", "sessions");
                Directory.CreateDirectory(destCache);
                foreach (var f in Directory.GetFiles(srcCache, "*.json"))
                    File.Copy(f, Path.Combine(destCache, Path.GetFileName(f)), true);
                log?.Invoke("会话缓存 " + Directory.GetFiles(srcCache, "*.json").Length + " 个");
            }

            // 3) 注册表
            JsonNode root;
            if (File.Exists(wsFile))
                root = JsonNode.Parse(File.ReadAllText(wsFile)) ?? new JsonObject();
            else
            {
                root = new JsonObject
                {
                    ["unit"] = new JsonObject { ["name"] = "workspace", ["version"] = 2 },
                    ["global"] = new JsonObject { ["initialized"] = true, ["workspaceIds"] = new JsonArray(), ["archivedSessionIds"] = new JsonArray() },
                    ["tables"] = new JsonObject { ["workspaces"] = new JsonObject() },
                };
            }
            var workspaces = root["tables"]?["workspaces"]?.AsObject();
            if (workspaces == null)
            {
                root["tables"] ??= new JsonObject();
                root["tables"]["workspaces"] = new JsonObject();
                workspaces = root["tables"]["workspaces"].AsObject();
            }

            // 会话 id 去重（目标机已有同名会话则跳过）
            sessionIds = sessionIds.Where(s => true).ToList();
            var newSessions = new JsonArray();
            foreach (var s in sessionIds) newSessions.Add(s);

            var entryNode = new JsonObject
            {
                ["path"] = destProject,
                ["title"] = title,
                ["sessionIds"] = newSessions,
            };
            workspaces[id] = entryNode;
            var ids = root["global"]?["workspaceIds"]?.AsArray();
            if (ids != null) ids.Add(id);

            var backup = wsFile + ".bak-" + DateTime.Now.ToString("yyyyMMdd-HHmmss");
            if (File.Exists(wsFile)) File.Copy(wsFile, backup, true);
            File.WriteAllText(wsFile, root.ToJsonString(),
                new UTF8Encoding(false));

            try { Directory.Delete(work, true); } catch { }
            return (true, $"已导入「{title}」到 {destProject}；重启实例后出现在项目列表里");
        }
        catch (Exception ex) { return (false, "导入失败：" + ex.Message); }
    }

    private static void AddFile(TarWriter tar, string file, string name)
    {
        try
        {
            var entry = new PaxTarEntry(TarEntryType.RegularFile, name) { DataStream = File.OpenRead(file) };
            tar.WriteEntry(entry);
            entry.DataStream?.Dispose();
        }
        catch { }
    }

    /// <summary>读取备份包的 manifest（预览用）。</summary>
    public static (string Title, string SourcePath, string CreatedAt, int Sessions, string DeviceShort)? ReadManifest(string bundlePath)
    {
        try
        {
            using var fs = File.OpenRead(bundlePath);
            using var gz = new GZipStream(fs, CompressionMode.Decompress);
            using var tar = new TarReader(gz);
            TarEntry e;
            while ((e = tar.GetNextEntry()) != null)
            {
                if (e.Name == "manifest.json" && e.DataStream != null)
                {
                    using var reader = new StreamReader(e.DataStream);
                    var node = JsonNode.Parse(reader.ReadToEnd());
                    if (node == null) return null;
                    return (node["Title"]?.GetValue<string>() ?? node["title"]?.GetValue<string>() ?? "项目",
                            node["SourcePath"]?.GetValue<string>() ?? node["sourcePath"]?.GetValue<string>() ?? "",
                            node["CreatedAt"]?.GetValue<string>() ?? node["createdAt"]?.GetValue<string>() ?? "",
                            0, "win-" + Environment.MachineName.ToLowerInvariant());
                }
            }
        }
        catch { }
        return null;
    }

    private static void AddText(TarWriter tar, string name, string text)
    {
        var bytes = Encoding.UTF8.GetBytes(text);
        var entry = new PaxTarEntry(TarEntryType.RegularFile, name) { DataStream = new MemoryStream(bytes) };
        tar.WriteEntry(entry);
    }

    private static void AddDir(TarWriter tar, string root, string prefix, CancellationToken ct = default,
        string[] skip = null)
    {
        skip ??= Array.Empty<string>();
        foreach (var file in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
        {
            ct.ThrowIfCancellationRequested();
            var rel = Path.GetRelativePath(root, file).Replace('\\', '/');
            if (skip.Any(s => rel.Split('/').Any(part => part.Equals(s, StringComparison.OrdinalIgnoreCase))))
                continue;
            try
            {
                var entry = new PaxTarEntry(TarEntryType.RegularFile, prefix + "/" + rel)
                {
                    DataStream = File.OpenRead(file),
                };
                tar.WriteEntry(entry);
                entry.DataStream?.Dispose();
            }
            catch { }
        }
    }

    private static void CopyDir(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (var dir in Directory.GetDirectories(src, "*", SearchOption.AllDirectories))
            Directory.CreateDirectory(dir.Replace(src, dst));
        foreach (var file in Directory.GetFiles(src, "*", SearchOption.AllDirectories))
        {
            var target = file.Replace(src, dst);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, true);
        }
    }
}
