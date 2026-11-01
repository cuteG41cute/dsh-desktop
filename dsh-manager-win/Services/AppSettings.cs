using System;
using System.IO;
using System.Text.Json;

namespace DshManager.Services;

/// <summary>管理器自己的偏好（目前只有日志行数，后面主题选择也并进来）。</summary>
public static class AppSettings
{
    public static int LogLines { get; set; } = 800;

    private sealed class Model
    {
        public int LogLines { get; set; } = 800;
    }

    private static string PathFile => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "dsh-manager", "settings.json");

    static AppSettings() => Load();

    public static void Load()
    {
        try
        {
            if (!File.Exists(PathFile)) return;
            var m = JsonSerializer.Deserialize<Model>(File.ReadAllText(PathFile));
            if (m != null && m.LogLines >= 100 && m.LogLines <= 5000) LogLines = m.LogLines;
        }
        catch { }
    }

    public static void Save()
    {
        try
        {
            var dir = Path.GetDirectoryName(PathFile);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(PathFile, JsonSerializer.Serialize(new Model { LogLines = LogLines },
                new JsonSerializerOptions { WriteIndented = true }));
        }
        catch { }
    }
}
