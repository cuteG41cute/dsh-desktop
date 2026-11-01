using System;
using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace DshManager.Services;

/// <summary>
/// 自签 DSH Web 认证 cookie（从 launcher.ps1 搬过来的算法）：
///   name  = "dsh-auth-" + base64url(sha256("host:port"))
///   value = "v1." + base64url(payload) + "." + base64url(hmac256(secret, base64url(payload)))
/// 用完先发一次真实请求验证（200 + __DSH_BOOT__），不通过就不注入。
/// </summary>
public static class AuthCookie
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(5) };

    public static (string Name, string Value, int Days)? Mint(int port)
    {
        var authority = "127.0.0.1:" + port;
        var secret = ReadSecret();
        if (string.IsNullOrEmpty(secret)) return null;
        foreach (var days in new[] { 30, 7, 1 })
        {
            var made = Build(authority, secret, days);
            if (made == null) continue;
            if (Verify(port, made.Value.Name, made.Value.Value)) return made;
        }
        return null;
    }

    private static (string Name, string Value, int Days)? Build(string authority, string secret, int days)
    {
        try
        {
            var key = FromBase64Url(secret);
            if (key.Length != 32) return null;
            using var sha = SHA256.Create();
            var name = "dsh-auth-" + ToBase64Url(sha.ComputeHash(Encoding.UTF8.GetBytes(authority)));

            var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            var expires = now + (long)days * 24 * 3600 * 1000;
            var json = "{\"version\":1,\"authority\":\"" + authority + "\",\"issuedAt\":" + now
                       + ",\"expiresAt\":" + expires + "}";
            var body = ToBase64Url(Encoding.UTF8.GetBytes(json));

            using var hmac = new HMACSHA256(key);
            var sig = ToBase64Url(hmac.ComputeHash(Encoding.UTF8.GetBytes(body)));
            return (name, "v1." + body + "." + sig, days);
        }
        catch { return null; }
    }

    private static bool Verify(int port, string name, string value)
    {
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, "http://127.0.0.1:" + port + "/");
            req.Headers.TryAddWithoutValidation("Cookie", name + "=" + value);
            using var resp = Http.Send(req);
            if (!resp.IsSuccessStatusCode) return false;
            return resp.Content.ReadAsStringAsync().GetAwaiter().GetResult().Contains("__DSH_BOOT__");
        }
        catch { return false; }
    }

    private static string ReadSecret()
    {
        try
        {
            var file = Path.Combine(DshDiscovery.HomeDir, ".credentials.yaml");
            if (!File.Exists(file)) return "";
            var m = Regex.Match(File.ReadAllText(file),
                @"client-connection/browser-session:.*?secret:\s*([A-Za-z0-9_\-]+)", RegexOptions.Singleline);
            return m.Success ? m.Groups[1].Value : "";
        }
        catch { return ""; }
    }

    private static string ToBase64Url(byte[] bytes) =>
        Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    private static byte[] FromBase64Url(string text)
    {
        var s = text.Replace('-', '+').Replace('_', '/');
        while (s.Length % 4 != 0) s += "=";
        return Convert.FromBase64String(s);
    }
}
