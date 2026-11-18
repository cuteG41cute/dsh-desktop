using System;
using System.IO;
using System.Text.Json;

namespace DshManager.Services;

/// <summary>管理器自己的偏好（日志行数、会话窗口增强、本地语音后端）。</summary>
public static class AppSettings
{
    public static int LogLines { get; set; } = 800;

    /// <summary>内置会话窗口：图片/PDF 放大后按住左键拖动平移（我们补的能力）。</summary>
    public static bool WebPan { get; set; } = true;

    /// <summary>内置会话窗口：文件树里的文件/目录行可以拖出到系统。</summary>
    public static bool WebDragOut { get; set; } = true;

    /// <summary>本地语音的推理后端：audiocpp / codec。</summary>
    public static string TtsBackend { get; set; } = "audiocpp";

    private sealed class Model
    {
        public int LogLines { get; set; } = 800;
        public bool WebPan { get; set; } = true;
        public bool WebDragOut { get; set; } = true;
        public string TtsBackend { get; set; } = "audiocpp";
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
            if (m != null)
            {
                WebPan = m.WebPan;
                WebDragOut = m.WebDragOut;
                if (!string.IsNullOrEmpty(m.TtsBackend)) TtsBackend = m.TtsBackend;
            }
        }
        catch { }
    }

    public static void Save()
    {
        try
        {
            var dir = Path.GetDirectoryName(PathFile);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(PathFile, JsonSerializer.Serialize(new Model
            {
                LogLines = LogLines,
                WebPan = WebPan,
                WebDragOut = WebDragOut,
                TtsBackend = TtsBackend,
            },
                new JsonSerializerOptions { WriteIndented = true }));
        }
        catch { }
    }
}
