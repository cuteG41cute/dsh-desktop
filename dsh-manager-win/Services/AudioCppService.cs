using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace DshManager.Services;

/// <summary>
/// audio.cpp 后端（通用多模型 TTS 引擎，ggml 原生）：
/// 按需下载官方发行包与 GGUF 模型，生成 server.json 并托管进程。
/// 对外仍是 OpenAI 兼容接口（/v1/models、/v1/audio/speech、/v1/audio/voices）。
/// </summary>
public static class AudioCppService
{
    public const int Port = 8092;

    private const string Gh = "https://github.com/0xShug0/audio.cpp/releases/download/v0.9.5/";
    private const string Mirror = "https://gh-proxy.com/";
    private const string Ms = "https://modelscope.cn/models/audio-cpp/audio.cpp-gguf/resolve/master/";
    private const string Bundle = "audio-v0.9.5-bin-windows-x64-cpu-portable.zip";

    public sealed record Model(string Id, string Label, string Family, string File,
                               string Remote, long Size, string DefaultVoice);

    public static readonly Model[] Models =
    {
        new("kokoro", "Kokoro-82M（快、54 音色）", "kokoro_tts",
            "kokoro-82m-q8_0.gguf", "Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf",
            189_644_800, "af_heart"),
        new("qwen3-tts", "Qwen3-TTS 0.6B（可克隆）", "qwen3_tts",
            "qwen3-tts-0.6b-base-q8_0.gguf", "Qwen3-TTS-12Hz-0.6B-Base-GGUF/qwen3-tts-12hz-0.6b-base-q8_0.gguf",
            2_040_000_000, ""),
    };

    public static string Root => Path.Combine(TtsService.Root, "..", "audiocpp");
    public static string BinDir => Path.Combine(Root, "bin");
    public static string ModelsDir => Path.Combine(Root, "models");
    public static string VoicesDir => Path.Combine(Root, "voices");
    public static string LogDir => Path.Combine(Root, "logs");
    public static string ConfigPath => Path.Combine(Root, "server.json");
    public static string ServerExe => Path.Combine(BinDir, "audiocpp_server.exe");

    public static bool RuntimeReady => File.Exists(ServerExe);

    public static string ModelPath(Model m) => Path.Combine(ModelsDir, m.File);

    public static bool ModelReady(Model m)
    {
        try
        {
            var p = ModelPath(m);
            return File.Exists(p) && new FileInfo(p).Length >= m.Size * 0.9;
        }
        catch { return false; }
    }

    public static List<Model> Installed() =>
        new(Array.FindAll(Models, ModelReady));

    public static bool Running => TtsService.PortOpen(Port);

    private static HttpClient Client()
    {
        var c = new HttpClient(ProxyConfig.Configure(new SocketsHttpHandler()))
        {
            Timeout = TimeSpan.FromMinutes(60),
        };
        return c;
    }

    /// <summary>下载并解压 Windows 发行包（约 32 MB）。</summary>
    public static async Task<(bool Ok, string Message)> DownloadRuntimeAsync(
        Action<long, long, string> progress, CancellationToken cancel = default)
    {
        if (RuntimeReady) return (true, "已安装");
        Directory.CreateDirectory(BinDir);
        var tmp = Path.Combine(Path.GetTempPath(), Bundle);
        var urls = new[] { Mirror + Gh + Bundle, Gh + Bundle };
        var (ok, err) = await DownloadAsync(urls, tmp, progress, Bundle, cancel);
        if (!ok) return (false, err);
        try
        {
            ZipFile.ExtractToDirectory(tmp, BinDir, true);
        }
        catch (Exception ex) { return (false, "解压失败：" + ex.Message); }
        if (!RuntimeReady)
        {
            foreach (var f in Directory.GetFiles(BinDir, "audiocpp_server.exe", SearchOption.AllDirectories))
            {
                var target = ServerExe;
                File.Copy(f, target, true);
                break;
            }
        }
        return RuntimeReady ? (true, "audio.cpp 已安装") : (false, "发行包里没有 audiocpp_server.exe");
    }

    public static Task<(bool Ok, string Message)> DownloadModelAsync(
        Model m, Action<long, long, string> progress, CancellationToken cancel = default)
    {
        if (ModelReady(m)) return Task.FromResult((true, "已存在"));
        Directory.CreateDirectory(ModelsDir);
        return DownloadAsync(new[] { Ms + m.Remote }, ModelPath(m), progress, m.File, cancel);
    }

    private static async Task<(bool Ok, string Message)> DownloadAsync(
        string[] urls, string dest, Action<long, long, string> progress, string label,
        CancellationToken cancel)
    {
        var part = dest + ".part";
        long have = File.Exists(part) ? new FileInfo(part).Length : 0;
        Exception last = null;
        using var http = Client();
        foreach (var url in urls)
        {
            try
            {
                using var req = new HttpRequestMessage(HttpMethod.Get, url);
                if (have > 0) req.Headers.Range = new System.Net.Http.Headers.RangeHeaderValue(have, null);
                using var resp = await http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, cancel);
                if (!resp.IsSuccessStatusCode) { last = new Exception("HTTP " + (int)resp.StatusCode); continue; }
                var total = have + (resp.Content.Headers.ContentLength ?? 0);
                if (resp.StatusCode != System.Net.HttpStatusCode.PartialContent) have = 0;
                await using (var fs = new FileStream(part, have > 0 ? FileMode.Append : FileMode.Create,
                                                     FileAccess.Write, FileShare.None))
                await using (var src = await resp.Content.ReadAsStreamAsync(cancel))
                {
                    var buf = new byte[1 << 20];
                    int n;
                    while ((n = await src.ReadAsync(buf, cancel)) > 0)
                    {
                        await fs.WriteAsync(buf.AsMemory(0, n), cancel);
                        have += n;
                        progress?.Invoke(have, total, label);
                    }
                }
                if (File.Exists(dest)) File.Delete(dest);
                File.Move(part, dest);
                return (true, "已下载 " + label);
            }
            catch (OperationCanceledException) { return (false, "已取消"); }
            catch (Exception ex) { last = ex; }
        }
        return (false, "下载失败：" + (last?.Message ?? "未知错误"));
    }

    public static void WriteConfig(IEnumerable<string> activeIds)
    {
        Directory.CreateDirectory(VoicesDir);
        var ids = new HashSet<string>(activeIds);
        var list = new List<object>();
        foreach (var m in Models)
        {
            if (!ids.Contains(m.Id) || !ModelReady(m)) continue;
            var entry = new Dictionary<string, object>
            {
                ["id"] = m.Id,
                ["family"] = m.Family,
                ["path"] = ModelPath(m),
                ["task"] = "tts",
                ["mode"] = "offline",
            };
            if (!string.IsNullOrEmpty(m.DefaultVoice))
                entry["default_voice_preset"] = new Dictionary<string, object> { ["voice_id"] = m.DefaultVoice };
            list.Add(entry);
        }
        var cfg = new Dictionary<string, object>
        {
            ["host"] = "127.0.0.1",
            ["port"] = Port,
            ["backend"] = "cpu",
            ["threads"] = Math.Max(2, Environment.ProcessorCount - 1),
            ["lazy_load"] = true,
            ["max_loaded_models"] = 1,
            ["ui"] = false,
            ["voice_dir"] = VoicesDir,
            ["models"] = list,
        };
        Directory.CreateDirectory(Root);
        File.WriteAllText(ConfigPath,
            JsonSerializer.Serialize(cfg, new JsonSerializerOptions { WriteIndented = true }));
    }

    public static (bool Ok, string Message) Start(IEnumerable<string> activeIds)
    {
        if (Running) return (true, "audio.cpp 已在运行");
        if (!RuntimeReady) return (false, "还没下载 audio.cpp 运行时");
        WriteConfig(activeIds);
        Directory.CreateDirectory(LogDir);
        var log = Path.Combine(LogDir, "server.log");
        Process.Start(new ProcessStartInfo
        {
            FileName = ServerExe,
            Arguments = "--config \"" + ConfigPath + "\"",
            WorkingDirectory = BinDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = false,
            RedirectStandardError = false,
        });
        for (var i = 0; i < 120; i++)
        {
            Thread.Sleep(500);
            if (Running) return (true, "audio.cpp 已启动（端口 " + Port + "）");
        }
        return (false, "启动超时，看日志：" + log);
    }

    public static (bool Ok, string Message) Stop()
    {
        if (!Running) return (true, "audio.cpp 已停止");
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = "taskkill",
                Arguments = "/F /IM audiocpp_server.exe",
                UseShellExecute = false,
                CreateNoWindow = true,
            })?.WaitForExit(5000);
        }
        catch { }
        for (var i = 0; i < 40; i++)
        {
            Thread.Sleep(250);
            if (!Running) return (true, "audio.cpp 已停止");
        }
        return (false, "停止失败：端口 " + Port + " 仍被占用");
    }

    public static List<string> ListModels()
    {
        var list = new List<string>();
        try
        {
            using var http = Client();
            var json = http.GetStringAsync($"http://127.0.0.1:{Port}/v1/models").GetAwaiter().GetResult();
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("data", out var data))
                foreach (var m in data.EnumerateArray())
                    if (m.TryGetProperty("id", out var id)) list.Add(id.GetString() ?? "");
        }
        catch { }
        return list;
    }

    public static List<string> Voices()
    {
        var list = new List<string>();
        try
        {
            using var http = Client();
            var json = http.GetStringAsync($"http://127.0.0.1:{Port}/v1/audio/voices").GetAwaiter().GetResult();
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("voices", out var v) && v.ValueKind == JsonValueKind.Array)
                foreach (var x in v.EnumerateArray()) list.Add(x.GetString() ?? "");
        }
        catch { }
        return list;
    }

    public static async Task<(bool Ok, string Error, string Wav, double Secs, TimeSpan Elapsed)> SynthesizeAsync(
        string text, string modelId, string voice)
    {
        if (!Running) return (false, "服务没在运行", "", 0, TimeSpan.Zero);
        try
        {
            var payload = new Dictionary<string, object>
            {
                ["model"] = modelId,
                ["input"] = text,
                ["response_format"] = "wav",
            };
            if (!string.IsNullOrWhiteSpace(voice)) payload["voice"] = voice;
            var sw = Stopwatch.StartNew();
            using var http = Client();
            using var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8,
                                                  "application/json");
            var resp = await http.PostAsync($"http://127.0.0.1:{Port}/v1/audio/speech", content);
            sw.Stop();
            if (!resp.IsSuccessStatusCode)
                return (false, await resp.Content.ReadAsStringAsync(), "", 0, sw.Elapsed);
            var bytes = await resp.Content.ReadAsByteArrayAsync();
            var dir = Path.Combine(Path.GetTempPath(), "dsh-manager-tts");
            Directory.CreateDirectory(dir);
            var wav = Path.Combine(dir, "acpp-" + DateTime.Now.ToString("HHmmss") + ".wav");
            await File.WriteAllBytesAsync(wav, bytes);
            var secs = bytes.Length > 44 ? (bytes.Length - 44) / 48000.0 : 0;
            return (true, "", wav, secs, sw.Elapsed);
        }
        catch (Exception ex) { return (false, ex.Message, "", 0, TimeSpan.Zero); }
    }
}
