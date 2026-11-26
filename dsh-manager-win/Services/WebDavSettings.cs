using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace DshManager.Services;

/// <summary>记住 WebDAV 地址/用户名/密码（密码用 DPAPI 加密，仅当前 Windows 用户可解）。</summary>
public static class WebDavSettings
{
    public sealed class Model
    {
        public string Url { get; set; } = "";
        public string User { get; set; } = "";
        public string Password { get; set; } = "";
    }

    private static string FilePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "dsh-manager", "webdav.json");

    public static Model Load()
    {
        try
        {
            if (!File.Exists(FilePath)) return null;
            var json = File.ReadAllText(FilePath, Encoding.UTF8);
            var stored = JsonSerializer.Deserialize<Stored>(json);
            if (stored == null) return null;
            var password = "";
            if (!string.IsNullOrEmpty(stored.Password))
            {
                var raw = Convert.FromBase64String(stored.Password);
                password = Encoding.UTF8.GetString(
                    ProtectedData.Unprotect(raw, null, DataProtectionScope.CurrentUser));
            }
            return new Model { Url = stored.Url ?? "", User = stored.User ?? "", Password = password };
        }
        catch { return null; }
    }

    public static void Save(string url, string user, string password)
    {
        try
        {
            var dir = Path.GetDirectoryName(FilePath)!;
            Directory.CreateDirectory(dir);
            var stored = new Stored { Url = url ?? "", User = user ?? "" };
            if (!string.IsNullOrEmpty(password))
            {
                var enc = ProtectedData.Protect(Encoding.UTF8.GetBytes(password), null,
                    DataProtectionScope.CurrentUser);
                stored.Password = Convert.ToBase64String(enc);
            }
            File.WriteAllText(FilePath,
                JsonSerializer.Serialize(stored, new JsonSerializerOptions { WriteIndented = true }),
                new UTF8Encoding(false));
        }
        catch { }
    }

    private sealed class Stored
    {
        public string Url { get; set; }
        public string User { get; set; }
        public string Password { get; set; }
    }
}
