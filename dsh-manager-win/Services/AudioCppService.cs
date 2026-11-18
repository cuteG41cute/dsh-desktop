using System;
using System.Collections.Generic;
using System.Linq;
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
            189_550_976, "af_heart"),
        new("moss-nano", "MOSS-TTS-Nano 100M（极小、快）", "moss_tts_nano",
            "moss-tts-nano-100m-q8_0.gguf", "MOSS-TTS-Nano-100M-GGUF/moss-tts-nano-100m-q8_0.gguf",
            193_343_328, ""),
        new("omnivoice", "OmniVoice（646 语言、克隆/设计）", "omnivoice",
            "omnivoice-q8_0.gguf", "OmniVoice-GGUF/omnivoice-q8_0.gguf",
            1_350_296_096, ""),
        new("irodori-anime", "Irodori-TTS v4.1 动漫（日系）", "irodori_tts",
            "irodori-tts-v4.1-anime-q8_0.gguf", "Irodori-TTS-v4-Small-GGUF/irodori-tts-v4.1-anime-q8_0.gguf",
            1_112_550_112, ""),
        new("qwen3-tts", "Qwen3-TTS 0.6B（可克隆音色）", "qwen3_tts",
            "qwen3-tts-0.6b-base-q8_0.gguf", "Qwen3-TTS-12Hz-0.6B-Base-GGUF/qwen3-tts-12hz-0.6b-base-q8_0.gguf",
            1_991_217_728, ""),
        new("cosyvoice3", "CosyVoice3（中文克隆/设计）", "cosyvoice3",
            "cosyvoice3-q8_0.gguf", "CosyVoice3-GGUF/cosyvoice3-q8_0.gguf",
            2_257_658_336, ""),
        new("chatterbox", "Chatterbox（英文表现力强）", "chatterbox",
            "chatterbox-q8_0.gguf", "Chatterbox-GGUF/chatterbox-q8_0.gguf",
            2_088_399_204, ""),
        new("index-tts2", "IndexTTS2.5（中文克隆最强档，3.3 GB）", "index_tts2",
            "index-tts2_5-q8_0.gguf", "IndexTTS2.5-GGUF/index-tts2_5-q8_0.gguf",
            3_502_960_096, ""),
    };

    public static string Root => Path.Combine(TtsService.Root, "..", "audiocpp");
    public static string BinDir => Path.Combine(Root, "bin");
    public static string ModelsDir => Path.Combine(Root, "models");
    public static string VoicesDir => Path.Combine(Root, "voices");
    public static string LogDir => Path.Combine(Root, "logs");
    public static string ConfigPath => Path.Combine(Root, "server.json");
    public static string ServerExe => Path.Combine(BinDir, "audiocpp_server.exe");

    public static bool RuntimeReady => File.Exists(ServerExe);

    /// <summary>
    /// 安装包里内嵌了 audio.cpp 运行时（带静态 eSpeak）。首次启动时释放到 bin/，
    /// 没有内嵌资源（开发构建）就什么都不做。
    /// </summary>
    public static void EnsureBundledRuntime()
    {
        try
        {
            Directory.CreateDirectory(BinDir);
            var asm = System.Reflection.Assembly.GetExecutingAssembly();
            var names = asm.GetManifestResourceNames();
            var exeName = names.FirstOrDefault(n => n.EndsWith("audiocpp_server.exe", StringComparison.OrdinalIgnoreCase));
            var dataName = names.FirstOrDefault(n => n.EndsWith("espeak-ng-data.bin", StringComparison.OrdinalIgnoreCase));
            if (exeName == null) return;   // 开发构建没带运行时

            var marker = Path.Combine(BinDir, "runtime.version");
            const string want = "audiocpp-espeak-v1";
            if (File.Exists(marker) && File.ReadAllText(marker).Trim() == want && File.Exists(ServerExe))
                return;

            using (var src = asm.GetManifestResourceStream(exeName))
            using (var dst = File.Create(ServerExe))
                src.CopyTo(dst);
            if (dataName != null)
            {
                using var src = asm.GetManifestResourceStream(dataName);
                using var dst = File.Create(Path.Combine(BinDir, "espeak-ng-data.bin"));
                src.CopyTo(dst);
            }
            File.WriteAllText(marker, want);
        }
        catch { }
    }

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

    private static HttpClient Client(bool useProxy = false)
    {
        // 这些下载目标（ModelScope / gh-proxy）在国内直连就能通；
        // 走用户残留的系统代理反而会卡死（请求发出去一个字节都不回）。
        var c = useProxy ? new HttpClient(ProxyConfig.Configure(new SocketsHttpHandler()))
                         : new HttpClient();
        c.Timeout = TimeSpan.FromMinutes(60);
        // ModelScope 的 CDN 会对没有 User-Agent 的请求直接回 403（curl 有 UA 所以能下）。
        c.DefaultRequestHeaders.UserAgent.ParseAdd("dsh-manager/3.2.3");
        c.DefaultRequestHeaders.Accept.ParseAdd("*/*");
        return c;
    }

    /// <summary>下载并解压 Windows 发行包（约 32 MB）。</summary>
    public static async Task<(bool Ok, string Message)> DownloadRuntimeAsync(
        Action<long, long, string> progress, CancellationToken cancel = default)
    {
        if (RuntimeReady) return (true, "已安装");
        Directory.CreateDirectory(BinDir);
        var tmp = Path.Combine(Path.GetTempPath(), Bundle);
        // 优先用我们自编译的「带静态 eSpeak」发行包（官方包对没有 eSpeak，英文音色会失败），
        // 拿不到再退回官方包。
        var ours = "https://github.com/cuteG41cute/dsh-desktop/releases/download/audio-cpp-espeak-v1/audio-cpp-espeak-win-x64.zip";
        var urls = new[] { ours, Mirror + Gh + Bundle, Gh + Bundle };
        var (ok, err) = await DownloadAsync(urls, tmp, 0, progress, Bundle, cancel);
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
        return DownloadAsync(new[] { Ms + m.Remote }, ModelPath(m), m.Size, progress, m.File, cancel);
    }

    /// <summary>
    /// 用系统自带的 curl.exe 分块下载：每块 64 MB，断了就从 .part 的现有长度继续。
    /// ModelScope 的 CDN 长连接会被中途掐断（约 500 MB 左右），整段下必失败；
    /// 分块 + 断点续传最稳，也能给界面一个稳定的进度来源。
    /// </summary>
    private static async Task<(bool Ok, string Message)> DownloadAsync(
        string[] urls, string dest, long expectedSize,
        Action<long, long, string> progress, string label, CancellationToken cancel)
    {
        const long Chunk = 64L * 1024 * 1024;
        var part = dest + ".part";
        // 旧的 .part 比目标还大 → 丢弃重来
        try
        {
            if (File.Exists(part) && expectedSize > 0 && new FileInfo(part).Length > expectedSize * 1.02)
                File.Delete(part);
        }
        catch { }

        Exception last = null;
        foreach (var url in urls)
        {
            var ok = true;
            var attempts = 0;
            while (ok)
            {
                long have = 0;
                try { if (File.Exists(part)) have = new FileInfo(part).Length; } catch { }
                if (expectedSize > 0 && have >= expectedSize) break;
                if (attempts++ > 80) { last = new Exception("重试次数过多"); ok = false; break; }

                var end = expectedSize > 0 ? Math.Min(expectedSize - 1, have + Chunk - 1) : 0;
                var chunkFile = part + ".chunk";
                try { if (File.Exists(chunkFile)) File.Delete(chunkFile); } catch { }

                var psi = new ProcessStartInfo
                {
                    FileName = "curl.exe",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardError = true,
                    RedirectStandardOutput = true,
                };
                psi.ArgumentList.Add("-4");
                psi.ArgumentList.Add("-L");
                psi.ArgumentList.Add("-sS");
                psi.ArgumentList.Add("--no-progress-meter");
                psi.ArgumentList.Add("-A"); psi.ArgumentList.Add("dsh-manager/3.2.4");
                psi.ArgumentList.Add("--max-time"); psi.ArgumentList.Add("900");
                if (expectedSize > 0)
                {
                    psi.ArgumentList.Add("-r");
                    psi.ArgumentList.Add(have.ToString() + "-" + end.ToString());
                }
                else if (have > 0)
                {
                    psi.ArgumentList.Add("-C"); psi.ArgumentList.Add("-");
                }
                psi.ArgumentList.Add("-o"); psi.ArgumentList.Add(chunkFile);
                psi.ArgumentList.Add(url);

                using var proc = Process.Start(psi);
                if (proc == null) { last = new Exception("无法启动 curl.exe"); ok = false; break; }

                while (!proc.HasExited)
                {
                    if (cancel.IsCancellationRequested)
                    {
                        try { proc.Kill(true); } catch { }
                        return (false, "已取消");
                    }
                    long len = 0;
                    try { if (File.Exists(part)) len += new FileInfo(part).Length; } catch { }
                    try { if (File.Exists(part + ".chunk")) len += new FileInfo(part + ".chunk").Length; } catch { }
                    progress?.Invoke(len, expectedSize, label);
                    await Task.Delay(400);
                }
                var err = proc.StandardError.ReadToEnd();
                if (proc.ExitCode != 0)
                {
                    last = new Exception("curl exit " + proc.ExitCode + ": " + err.Trim());
                    // 有些分块失败可以跳过重试，交给下一轮循环继续
                    await Task.Delay(1500);
                    continue;
                }

                long got = 0;
                try { if (File.Exists(chunkFile)) got = new FileInfo(chunkFile).Length; } catch { }
                if (got == 0)
                {
                    long cur = 0;
                    try { if (File.Exists(part)) cur = new FileInfo(part).Length; } catch { }
                    if (expectedSize > 0 && cur >= expectedSize * 0.98) break;   // 服务端已经没有更多数据了
                    last = new Exception("分块为空（" + cur + "/" + expectedSize + "）");
                    await Task.Delay(1500);
                    continue;
                }
                if (expectedSize > 0 && have + got > expectedSize)
                {
                    // 服务端忽略 Range 时会把整文件塞回来：只有第一块才接受
                    if (have == 0 && got == expectedSize) { File.Move(chunkFile, part); }
                    else { try { File.Delete(chunkFile); } catch { } last = new Exception("分块长度异常"); continue; }
                }
                else
                {
                    await using (var src = new FileStream(chunkFile, FileMode.Open, FileAccess.Read, FileShare.Read))
                    await using (var dst = new FileStream(part, FileMode.Append, FileAccess.Write, FileShare.None))
                        await src.CopyToAsync(dst, cancel);
                }
                try { File.Delete(chunkFile); } catch { }
                progress?.Invoke(new FileInfo(part).Length, expectedSize, label);
            }

            if (!ok) continue;
            long size = 0;
            try { size = new FileInfo(part).Length; } catch { }
            if (expectedSize > 0 && size < expectedSize * 0.98)
            {
                last = new Exception("文件不完整：" + size + "/" + expectedSize);
                continue;
            }
            if (dest.EndsWith(".gguf", StringComparison.OrdinalIgnoreCase) && !LooksLikeGguf(part))
            {
                last = new Exception("下载内容不是 GGUF（可能被拦截或截断）");
                try { File.Delete(part); } catch { }
                continue;
            }
            try { if (File.Exists(dest)) File.Delete(dest); } catch { }
            File.Move(part, dest);
            progress?.Invoke(size, expectedSize > 0 ? expectedSize : size, label);
            return (true, "已下载 " + label);
        }
        return (false, "下载失败：" + (last?.Message ?? "未知错误"));
    }

    private static bool LooksLikeGguf(string path)
    {
        try
        {
            using var fs = File.OpenRead(path);
            var buf = new byte[4];
            return fs.Read(buf, 0, 4) == 4 && buf[0] == (byte)'G' && buf[1] == (byte)'G'
                   && buf[2] == (byte)'U' && buf[3] == (byte)'F';
        }
        catch { return false; }
    }

    private static void DbLog(string msg)
    {
        try { File.AppendAllText(Path.Combine(Path.GetTempPath(), "dsh-dl-debug.log"),
                                 DateTime.Now.ToString("HH:mm:ss") + " " + msg + Environment.NewLine); } catch { }
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

    /// <summary>Kokoro 的内置音色（audio.cpp 不走 /v1/audio/voices 暴露 preset，这里按官方列表内置）。</summary>
    public static readonly string[] KokoroVoices =
    {
        "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore", "af_nicole",
        "af_nova", "af_river", "af_sarah", "af_sky",
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx",
        "am_puck", "am_santa",
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
        "ef_dora", "em_alex", "ff_siwis",
        "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
        "if_sara", "im_nicola",
        "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
        "pf_dora", "pm_alex", "pm_santa",
        "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
        "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    };

    public static List<string> PresetVoices(string modelId)
    {
        if (modelId == "kokoro") return new List<string>(KokoroVoices);
        return new List<string>();
    }

    /// <summary>新建音色：把参考音频转成 24k 单声道放进 voice_dir，并登记参考文本。</summary>
    public static (bool Ok, string Message) AddVoice(string name, string wavPath, string refText)
    {
        try
        {
            Directory.CreateDirectory(VoicesDir);
            var dest = Path.Combine(VoicesDir, name + ".wav");
            File.Copy(wavPath, dest, true);

            var promptFile = Path.Combine(VoicesDir, "prompt_text");
            var lines = new List<string>();
            if (File.Exists(promptFile))
                lines.AddRange(File.ReadAllLines(promptFile).Where(l => !string.IsNullOrWhiteSpace(l)
                    && !l.Split('|')[0].Trim().Equals(name, StringComparison.OrdinalIgnoreCase)));
            lines.Add(name + "|" + (refText ?? "").Trim());
            File.WriteAllLines(promptFile, lines, new UTF8Encoding(false));
            return (true, "音色已创建：" + name);
        }
        catch (Exception ex) { return (false, "创建失败：" + ex.Message); }
    }

    public static List<string> ListModels()
    {
        var list = new List<string>();
        try
        {
            using var http = Client();
            http.Timeout = TimeSpan.FromSeconds(5);
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
            http.Timeout = TimeSpan.FromSeconds(5);
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
