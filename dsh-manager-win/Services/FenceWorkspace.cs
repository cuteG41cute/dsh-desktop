using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace DshManager.Services;

/// <summary>通过 dsh-fence 插件的 HTTP 入口，在用户级实例围栏内按名称新建工作区。</summary>
public static class FenceWorkspace
{
    public static async Task<(bool Ok, string Message)> CreateAsync(DshInstance inst, string name)
    {
        if (string.IsNullOrWhiteSpace(name)) return (false, "工作区名称不能为空");
        var cookie = AuthCookie.Mint(inst.Port, inst.Home);
        if (cookie == null) return (false, "拿不到实例认证凭据");
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
            using var req = new HttpRequestMessage(HttpMethod.Post,
                "http://127.0.0.1:" + inst.Port + "/dsh-fence/create");
            req.Headers.TryAddWithoutValidation("Cookie", cookie.Value.Name + "=" + cookie.Value.Value);
            req.Content = new StringContent(
                JsonSerializer.Serialize(new { name }),
                Encoding.UTF8, "application/json");
            using var resp = await http.SendAsync(req);
            var text = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(string.IsNullOrWhiteSpace(text) ? "{}" : text);
            var root = doc.RootElement;
            if (root.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True)
            {
                var path = root.TryGetProperty("path", out var p) ? p.GetString() : "";
                return (true, "已在围栏内创建工作区：" + path);
            }
            var err = root.TryGetProperty("error", out var e) ? e.GetString() : text;
            return (false, "创建失败：" + err);
        }
        catch (Exception ex) { return (false, "调用围栏接口失败：" + ex.Message); }
    }
}
