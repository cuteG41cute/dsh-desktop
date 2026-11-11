using System;
using System.Diagnostics;
using System.Net;
using System.Net.Http;
using Microsoft.Win32;

namespace DshManager.Services;

/// <summary>
/// 代理探测：装了 VPN / 代理软件时，「更新版本、下载 Node、git clone、pnpm install」
/// 这些走网络的操作**优先走系统代理**，而不是硬直连。
///
/// 探测顺序：
///   1) 环境变量 HTTPS_PROXY / HTTP_PROXY / ALL_PROXY（用户显式设过就以它为准）；
///   2) Windows「Internet 选项」里的代理（注册表 ProxyEnable + ProxyServer，例如 127.0.0.1:7890）；
///   3) 都没有 → 直连。
/// </summary>
public static class ProxyConfig
{
    private static string _cached;
    private static bool _resolved;

    /// <summary>当前要用的代理地址（http://host:port），没有就返回 null。</summary>
    public static string Current
    {
        get
        {
            if (_resolved) return _cached;
            _resolved = true;
            _cached = Detect();
            return _cached;
        }
    }

    /// <summary>探测到的原始代理（未做连通性检查），供 Describe 说明「配置了但连不上」。</summary>
    public static string ConfiguredButUnreachable { get; private set; }

    private static string Detect()
    {
        // 1) 环境变量（大小写都查：Windows 上两种都见过）
        foreach (var name in new[] { "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy" })
        {
            var v = Environment.GetEnvironmentVariable(name);
            if (!string.IsNullOrWhiteSpace(v))
            {
                var candidate = Normalize(v);
                if (IsReachable(candidate)) return candidate;
                ConfiguredButUnreachable = candidate;
                return null;
            }
        }

        // 2) 系统代理（注册表）
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(
                @"Software\Microsoft\Windows\CurrentVersion\Internet Settings");
            if (key != null)
            {
                var enabled = key.GetValue("ProxyEnable") as int? ?? 0;
                if (enabled != 0)
                {
                    var server = key.GetValue("ProxyServer") as string;
                    if (!string.IsNullOrWhiteSpace(server))
                    {
                        var candidate = Normalize(server);
                        if (IsReachable(candidate)) return candidate;
                        // 系统里配着代理、但代理软件没开（很常见：上次留下的 127.0.0.1:7890）
                        // —— 这时候如果硬走代理，git/pnpm 会全部失败，所以回退直连。
                        ConfiguredButUnreachable = candidate;
                        return null;
                    }
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private static bool IsReachable(string proxy)
    {
        try
        {
            var u = new Uri(proxy);
            using var client = new System.Net.Sockets.TcpClient();
            var task = client.ConnectAsync(u.Host, u.Port == -1 ? 80 : u.Port);
            return task.Wait(TimeSpan.FromMilliseconds(600)) && client.Connected;
        }
        catch
        {
            return false;
        }
    }

    private static string Normalize(string raw)
    {
        var s = raw.Trim();
        if (s.Contains('='))
        {
            // "http=127.0.0.1:7890;https=127.0.0.1:7890" 这种形式：取 https，其次 http
            var parts = s.Split(';', StringSplitOptions.RemoveEmptyEntries);
            string pick = null;
            foreach (var p in parts)
            {
                var kv = p.Split('=', 2);
                if (kv.Length != 2) continue;
                var k = kv[0].Trim().ToLowerInvariant();
                if (k == "https") { pick = kv[1].Trim(); break; }
                if (k == "http" && pick == null) pick = kv[1].Trim();
            }
            if (pick != null) s = pick;
        }
        if (s.StartsWith("http://", StringComparison.OrdinalIgnoreCase) ||
            s.StartsWith("https://", StringComparison.OrdinalIgnoreCase) ||
            s.StartsWith("socks", StringComparison.OrdinalIgnoreCase))
        {
            return s;
        }
        return "http://" + s;
    }

    /// <summary>把代理写进子进程环境（git / npm / pnpm / node 都会读这些变量）。</summary>
    public static void ApplyTo(ProcessStartInfo psi)
    {
        var proxy = Current;
        if (proxy == null) return;
        try
        {
            psi.Environment["HTTP_PROXY"] = proxy;
            psi.Environment["HTTPS_PROXY"] = proxy;
            psi.Environment["ALL_PROXY"] = proxy;
            psi.Environment["http_proxy"] = proxy;
            psi.Environment["https_proxy"] = proxy;
            // git 认这个变量的优先级更高（有些发行版里 curl 不读小写）
            psi.Environment["GIT_HTTP_PROXY"] = proxy;
        }
        catch
        {
        }
    }

    /// <summary>给 HttpClient 配上代理（下载 Node、查版本列表、GitHub API 都走这里）。</summary>
    public static HttpMessageHandler Configure(HttpMessageHandler handler)
    {
        var proxy = Current;
        if (proxy == null) return handler;
        try
        {
            if (handler is SocketsHttpHandler s)
            {
                s.UseProxy = true;
                s.Proxy = new WebProxy(proxy);
            }
            else if (handler is HttpClientHandler h)
            {
                h.UseProxy = true;
                h.Proxy = new WebProxy(proxy);
            }
        }
        catch
        {
        }
        return handler;
    }

    /// <summary>日志用的一句话说明当前网络策略。</summary>
    public static string Describe()
    {
        var proxy = Current;
        if (proxy != null) return "使用代理 " + proxy;
        return ConfiguredButUnreachable != null
            ? "检测到代理 " + ConfiguredButUnreachable + " 但连不上，已回退直连"
            : "未检测到代理，直连";
    }
}
