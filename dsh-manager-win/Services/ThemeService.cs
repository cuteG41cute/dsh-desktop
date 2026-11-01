using System;
using System.IO;
using System.Text.Json;
using System.Windows;

namespace DshManager.Services;

/// <summary>
/// 主题服务：7 套主题 × 昼/夜，配色来自 Linux 版已经验证过的 themes.json
/// （由 tools/gen-win-themes.py 生成 14 个资源字典）。
/// </summary>
public static class ThemeService
{
    public static readonly (string Id, string Label, string Hint, string Swatch)[] Themes =
    {
        ("frost", "毛玻璃", "柔和透明", "#8b7cf6"),
        ("liquid", "液态玻璃", "流动高光", "#4f8dff"),
        ("crystal", "水晶", "清透棱角", "#38bdd1"),
        ("flat", "扁平化", "简洁高效", "#4f46e5"),
        ("alpine", "雪山", "纯净凛冽", "#5a8fc4"),
        ("dawn", "晨光", "温暖轻盈", "#ef956f"),
        ("sea", "静海", "沉静深邃", "#258e92"),
    };

    public static string Theme { get; private set; } = "frost";
    public static string Mode { get; private set; } = "day";

    public static string Label =>
        Array.Find(Themes, t => t.Id == Theme).Label ?? Theme;

    private static ResourceDictionary _current;

    public static void Init()
    {
        var s = Load();
        Theme = s.Theme;
        Mode = s.Mode;
        Apply();
    }

    public static void SetTheme(string id)
    {
        Theme = id;
        Apply();
        Save();
    }

    public static void ToggleMode()
    {
        Mode = Mode == "day" ? "night" : "day";
        Apply();
        Save();
    }

    /// <summary>把当前主题的资源字典替换进来（其余资源不动）。</summary>
    public static void Apply()
    {
        var app = Application.Current;
        var uri = new Uri($"Themes/{Theme}-{Mode}.xaml", UriKind.Relative);
        var dict = new ResourceDictionary { Source = uri };
        if (_current != null)
            app.Resources.MergedDictionaries.Remove(_current);
        app.Resources.MergedDictionaries.Add(dict);
        _current = dict;
        ThemeChanged?.Invoke();
    }

    public static event Action ThemeChanged;

    // ---------------------------------------------------------------- 持久化
    private sealed class State
    {
        public string Theme { get; set; } = "frost";
        public string Mode { get; set; } = "day";
    }

    private static string StatePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "dsh-manager", "win-settings.json");

    private static State Load()
    {
        try
        {
            if (File.Exists(StatePath))
                return JsonSerializer.Deserialize<State>(File.ReadAllText(StatePath)) ?? new State();
        }
        catch { }
        return new State();
    }

    private static void Save()
    {
        try
        {
            var dir = Path.GetDirectoryName(StatePath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(StatePath, JsonSerializer.Serialize(new State { Theme = Theme, Mode = Mode }));
        }
        catch { }
    }
}
