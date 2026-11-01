using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

namespace DshManager.Services;

/// <summary>管理器自己创建的实例（自定义目录不会被 DshDiscovery 的固定位置扫到，所以单独登记）。</summary>
public sealed class RegistryEntry
{
    public string Id { get; set; } = "";
    public string Label { get; set; } = "";
    public string Dir { get; set; } = "";
    public int Port { get; set; }
    public string DshVersion { get; set; } = "";
    /// <summary>实例自带的 Node 版本（空/&quot;system&quot; = 用系统 node）。</summary>
    public string NodeVersion { get; set; } = "";
    public string CreatedAt { get; set; } = "";
}

public static class InstanceRegistry
{
    private static string PathFile => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "dsh-manager", "instances.json");

    public static List<RegistryEntry> Load()
    {
        try
        {
            if (!File.Exists(PathFile)) return new List<RegistryEntry>();
            var list = JsonSerializer.Deserialize<List<RegistryEntry>>(File.ReadAllText(PathFile));
            return list ?? new List<RegistryEntry>();
        }
        catch { return new List<RegistryEntry>(); }
    }

    public static void Save(List<RegistryEntry> list)
    {
        try
        {
            var dir = Path.GetDirectoryName(PathFile);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(PathFile, JsonSerializer.Serialize(list,
                new JsonSerializerOptions { WriteIndented = true }));
        }
        catch { }
    }

    public static void Add(RegistryEntry entry)
    {
        var list = Load();
        // 同一个目录只留一条：id 曾经用 GetHashCode()（每个进程都不同），
        // 老版本留下过重复登记，这里顺手清掉。
        list.RemoveAll(e => string.Equals(e.Id, entry.Id, StringComparison.OrdinalIgnoreCase)
                            || SamePath(e.Dir, entry.Dir));
        list.Add(entry);
        Save(list);
    }

    public static bool Remove(string id)
    {
        var list = Load();
        var n = list.RemoveAll(e => string.Equals(e.Id, id, StringComparison.OrdinalIgnoreCase));
        Save(list);
        return n > 0;
    }

    /// <summary>按目录移除（卸载时用这个更稳：登记表里可能有历史重复项）。</summary>
    public static bool RemoveByDir(string dir)
    {
        var list = Load();
        var n = list.RemoveAll(e => SamePath(e.Dir, dir));
        Save(list);
        return n > 0;
    }

    private static bool SamePath(string a, string b)
    {
        if (string.IsNullOrWhiteSpace(a) || string.IsNullOrWhiteSpace(b)) return false;
        try { return string.Equals(Path.GetFullPath(a), Path.GetFullPath(b), StringComparison.OrdinalIgnoreCase); }
        catch { return false; }
    }

    public static RegistryEntry Find(string id) =>
        Load().Find(e => string.Equals(e.Id, id, StringComparison.OrdinalIgnoreCase));

    /// <summary>默认安装根目录：%LOCALAPPDATA%\dsh-manager\instances</summary>
    public static string DefaultRoot => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "dsh-manager", "instances");
}
