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
        list.RemoveAll(e => string.Equals(e.Id, entry.Id, StringComparison.OrdinalIgnoreCase));
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

    public static RegistryEntry Find(string id) =>
        Load().Find(e => string.Equals(e.Id, id, StringComparison.OrdinalIgnoreCase));

    /// <summary>默认安装根目录：%LOCALAPPDATA%\dsh-manager\instances</summary>
    public static string DefaultRoot => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "dsh-manager", "instances");
}
