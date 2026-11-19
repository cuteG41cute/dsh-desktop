using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;

namespace DshManager.Services;

/// <summary>最小 WebDAV 客户端：测试连接、列目录、上传、下载。</summary>
public sealed class WebDavClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string _user;
    private readonly string _pass;

    public WebDavClient(string user, string pass, int timeoutSeconds = 60)
    {
        _user = user ?? "";
        _pass = pass ?? "";
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(timeoutSeconds) };
        if (_user.Length > 0)
        {
            var token = Convert.ToBase64String(Encoding.UTF8.GetBytes(_user + ":" + _pass));
            _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Basic", token);
        }
    }

    public async Task<(bool Ok, string Message, int Code)> TestAsync(string url)
    {
        try
        {
            using var req = new HttpRequestMessage(new HttpMethod("PROPFIND"), NormalizeUrl(url));
            req.Headers.Add("Depth", "0");
            var res = await _http.SendAsync(req);
            var code = (int)res.StatusCode;
            return (code is >= 200 and < 400, "HTTP " + code, code);
        }
        catch (Exception ex) { return (false, ex.Message, 0); }
    }

    public sealed record DavEntry(string Url, string Name, bool IsDirectory, long Size, DateTime? Modified);

    public async Task<List<DavEntry>> ListAsync(string url)
    {
        var list = new List<DavEntry>();
        var baseUri = new Uri(NormalizeUrl(url).TrimEnd('/') + "/");
        using var req = new HttpRequestMessage(new HttpMethod("PROPFIND"), baseUri);
        req.Headers.Add("Depth", "1");
        var res = await _http.SendAsync(req);
        var text = await res.Content.ReadAsStringAsync();
        if (!res.IsSuccessStatusCode) throw new IOException("HTTP " + (int)res.StatusCode + " " + text.Substring(0, Math.Min(200, text.Length)));
        var doc = XDocument.Parse(text);
        XNamespace d = "DAV:";
        foreach (var resp in doc.Descendants(d + "response"))
        {
            var href = resp.Element(d + "href")?.Value ?? "";
            if (href.Length == 0) continue;
            var props = resp.Descendants(d + "prop").FirstOrDefault();
            var isDir = props?.Element(d + "resourcetype")?.Element(d + "collection") != null;
            var lenText = props?.Element(d + "getcontentlength")?.Value;
            var modText = props?.Element(d + "getlastmodified")?.Value;
            long.TryParse(lenText, out var size);
            DateTime? mod = null;
            if (DateTime.TryParse(modText, out var m)) mod = m;
            var name = Uri.UnescapeDataString(new Uri(baseUri, href).AbsolutePath);
            name = name.TrimEnd('/');
            name = name.Substring(name.LastIndexOf('/') + 1);
            if (name.Length == 0) continue;
            list.Add(new DavEntry(new Uri(baseUri, href).ToString(), name, isDir, size, mod));
        }
        return list;
    }

    public async Task UploadAsync(string localFile, string remoteUrl, Action<long, long> progress = null,
        CancellationToken ct = default)
    {
        var info = new FileInfo(localFile);
        using var fs = File.OpenRead(localFile);
        using var req = new HttpRequestMessage(HttpMethod.Put, NormalizeUrl(remoteUrl)) { Content = new StreamContent(fs) };
        req.Content.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        req.Content.Headers.ContentLength = info.Length;
        var res = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
        if (!res.IsSuccessStatusCode)
            throw new IOException("上传失败：HTTP " + (int)res.StatusCode);
        progress?.Invoke(info.Length, info.Length);
    }

    public async Task DownloadAsync(string remoteUrl, string localFile, CancellationToken ct = default)
    {
        using var res = await _http.GetAsync(NormalizeUrl(remoteUrl), HttpCompletionOption.ResponseHeadersRead, ct);
        if (!res.IsSuccessStatusCode) throw new IOException("下载失败：HTTP " + (int)res.StatusCode);
        await using var fs = File.Create(localFile);
        await res.Content.CopyToAsync(fs, ct);
    }

    public async Task<(bool Ok, string Message)> EnsureCollectionAsync(string url)
    {
        try
        {
            var res = await _http.SendAsync(new HttpRequestMessage(new HttpMethod("MKCOL"), NormalizeUrl(url)));
            var code = (int)res.StatusCode;
            return (code is 200 or 201 or 405, "HTTP " + code);
        }
        catch (Exception ex) { return (false, ex.Message); }
    }

    private static string NormalizeUrl(string url)
    {
        url = (url ?? "").Trim();
        if (!url.StartsWith("http", StringComparison.OrdinalIgnoreCase)) url = "https://" + url;
        return url;
    }

    public void Dispose() => _http.Dispose();
}
