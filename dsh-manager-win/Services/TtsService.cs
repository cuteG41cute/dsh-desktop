using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Threading.Tasks;

namespace DshManager.Services;

/// <summary>
/// 本地语音服务（Qwen3-TTS）：管理器只管「起进程 / 停进程 / 看状态 / 打开管理页」。
/// 运行资产放在 %LOCALAPPDATA%\dsh-manager\services\tts（run / models / voices / dashboard）。
/// </summary>
public static class TtsService
{
    public static string Root =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                     "dsh-manager", "services", "tts");

    public static string RunDir => Path.Combine(Root, "run");
    public static string ModelsDir => Path.Combine(Root, "models");
    public static string VoicesDir => Path.Combine(Root, "voices");
    public static string DashboardDir => Path.Combine(Root, "dashboard");
    public static string LogDir => Path.Combine(Root, "logs");

    public const int Port = 8098;
    public const int DashboardPort = 8097;

    public static string ServerExe => Path.Combine(RunDir, "tts-server.exe");
    public static string BackbonePath => Path.Combine(ModelsDir, "qwen3-tts-0.6b-q8_0.gguf");
    public static string CodecPath => Path.Combine(ModelsDir, "codec-q8_0.gguf");

    /// <summary>模型两个文件都在，才算「已就绪」。</summary>
    public static bool ModelsReady => File.Exists(BackbonePath) && File.Exists(CodecPath);
    public static bool BinariesReady => File.Exists(ServerExe);

    public static long ModelsBytes
    {
        get
        {
            long sum = 0;
            foreach (var p in new[] { BackbonePath, CodecPath })
            {
                try { if (File.Exists(p)) sum += new FileInfo(p).Length; } catch { }
            }
            return sum;
        }
    }

    private static Process _server;
    private static Process _dashboard;

    public static bool PortOpen(int port)
    {
        try
        {
            using var c = new TcpClient();
            var t = c.ConnectAsync("127.0.0.1", port);
            return t.Wait(400) && c.Connected;
        }
        catch { return false; }
    }

    public static bool Running => PortOpen(Port);
    public static bool DashboardRunning => PortOpen(DashboardPort);

    /// <summary>拉起 tts-server（已就绪就什么都不做）。</summary>
    public static (bool Ok, string Message) Start()
    {
        if (!BinariesReady) return (false, "缺少 tts-server.exe：" + RunDir);
        if (!ModelsReady) return (false, "模型没下载完整，需要两个 GGUF：" + ModelsDir);
        if (Running) return (true, "已经在运行");

        try
        {
            Directory.CreateDirectory(LogDir);
            var args = $"--backbone \"{BackbonePath}\" --model \"{CodecPath}\" --host 127.0.0.1 " +
                       $"--port {Port} --voice-dir \"{VoicesDir}\" --allow-voice-create --n-threads 8";
            var psi = new ProcessStartInfo(ServerExe, args)
            {
                WorkingDirectory = RunDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            ProxyConfig.ApplyTo(psi);
            var logFile = Path.Combine(LogDir, "server.log");
            var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
            proc.OutputDataReceived += (_, e) => Append(logFile, e.Data);
            proc.ErrorDataReceived += (_, e) => Append(logFile, e.Data);
            proc.Exited += (_, _) => { try { _server = null; } catch { } };
            proc.Start();
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            _server = proc;
            return (true, "启动中（模型加载十几秒）");
        }
        catch (Exception ex)
        {
            return (false, "启动失败：" + ex.Message);
        }
    }

    public static (bool Ok, string Message) Stop()
    {
        try
        {
            if (_server != null && !_server.HasExited)
            {
                _server.Kill(true);
                _server = null;
                return (true, "已停止");
            }
            var pid = PidOnPort(Port);
            if (pid > 0)
            {
                Process.Start(new ProcessStartInfo("taskkill", $"/PID {pid} /T /F")
                { UseShellExecute = false, CreateNoWindow = true })?.WaitForExit(3000);
                return (true, $"已停止（进程 {pid}）");
            }
            return (false, "没有在运行");
        }
        catch (Exception ex) { return (false, "停止失败：" + ex.Message); }
    }

    /// <summary>拉起管理页（node server.js），然后返回地址。已经跑着就只返回地址。</summary>
    public static (bool Ok, string Url) EnsureDashboard()
    {
        var url = $"http://127.0.0.1:{DashboardPort}/";
        if (DashboardRunning) return (true, url);
        var node = FindNode();
        if (node == null) return (false, "找不到 node.exe，无法启动管理页");
        var serverJs = Path.Combine(DashboardDir, "server.js");
        if (!File.Exists(serverJs)) return (false, "缺少管理页脚本：" + serverJs);
        try
        {
            var psi = new ProcessStartInfo(node, "server.js")
            {
                WorkingDirectory = DashboardDir,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            var p = Process.Start(psi);
            _dashboard = p;
            return (true, url);
        }
        catch (Exception ex) { return (false, "管理页启动失败：" + ex.Message); }
    }

    private static string FindNode()
    {
        var candidates = new[]
        {
            @"C:\Program Files\nodejs\node.exe",
            @"C:\Program Files (x86)\nodejs\node.exe",
        };
        foreach (var c in candidates) if (File.Exists(c)) return c;
        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var part in path.Split(';'))
        {
            if (string.IsNullOrWhiteSpace(part)) continue;
            try
            {
                var p = Path.Combine(part.Trim(), "node.exe");
                if (File.Exists(p)) return p;
            }
            catch { }
        }
        return null;
    }

    private static int PidOnPort(int port)
    {
        try
        {
            var psi = new ProcessStartInfo("netstat", "-ano -p TCP")
            { UseShellExecute = false, RedirectStandardOutput = true, CreateNoWindow = true };
            using var p = Process.Start(psi);
            var text = p?.StandardOutput.ReadToEnd() ?? "";
            p?.WaitForExit(2000);
            foreach (var line in text.Split('\n'))
            {
                if (!line.Contains($":{port} ")) continue;
                if (!line.Contains("LISTENING", StringComparison.OrdinalIgnoreCase)) continue;
                var parts = line.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length > 0 && int.TryParse(parts[^1], out var pid)) return pid;
            }
        }
        catch { }
        return 0;
    }

    // ---------------------------------------------------------------- 管理页功能（内嵌）

    public sealed class VoiceInfo
    {
        public string Id { get; set; } = "";
        public string Name { get; set; } = "";
    }

    private static HttpClient Client()
    {
        var c = new HttpClient(ProxyConfig.Configure(new SocketsHttpHandler()))
        {
            Timeout = TimeSpan.FromMinutes(10),
        };
        return c;
    }

    /// <summary>列出自定义音色。</summary>
    public static async Task<(bool Ok, string Error, List<VoiceInfo> Voices)> ListVoicesAsync()
    {
        var list = new List<VoiceInfo>();
        if (!Running) return (false, "服务没在运行", list);
        try
        {
            using var c = Client();
            var json = await c.GetStringAsync($"http://127.0.0.1:{Port}/v1/audio/voices");
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("custom", out var arr) && arr.ValueKind == JsonValueKind.Array)
            {
                foreach (var v in arr.EnumerateArray())
                {
                    list.Add(new VoiceInfo
                    {
                        Id = v.TryGetProperty("id", out var id) ? id.GetString() ?? "" : "",
                        Name = v.TryGetProperty("name", out var name) ? name.GetString() ?? "" : "",
                    });
                }
            }
            return (true, "", list);
        }
        catch (Exception ex) { return (false, ex.Message, list); }
    }

    /// <summary>用一段参考音频克隆音色（multipart 上传给 tts-server）。</summary>
    public static async Task<(bool Ok, string Message)> CreateVoiceAsync(string name, string wavPath)
    {
        if (!Running) return (false, "服务没在运行");
        try
        {
            using var c = Client();
            using var form = new MultipartFormDataContent();
            form.Add(new StringContent(name), "name");
            var bytes = await File.ReadAllBytesAsync(wavPath);
            var file = new ByteArrayContent(bytes);
            file.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("audio/wav");
            form.Add(file, "audio_sample", Path.GetFileName(wavPath));
            var resp = await c.PostAsync($"http://127.0.0.1:{Port}/v1/audio/voices", form);
            var text = await resp.Content.ReadAsStringAsync();
            return (resp.IsSuccessStatusCode, resp.IsSuccessStatusCode ? ("已创建音色：" + name) : text);
        }
        catch (Exception ex) { return (false, "上传失败：" + ex.Message); }
    }

    public static async Task<(bool Ok, string Message)> DeleteVoiceAsync(string id)
    {
        if (!Running) return (false, "服务没在运行");
        try
        {
            using var c = Client();
            var resp = await c.DeleteAsync($"http://127.0.0.1:{Port}/v1/audio/voices/{id}");
            return (resp.IsSuccessStatusCode, resp.IsSuccessStatusCode ? "已删除" : ("删除失败：" + (int)resp.StatusCode));
        }
        catch (Exception ex) { return (false, "删除失败：" + ex.Message); }
    }

    /// <summary>合成一段语音，返回临时 wav 路径和耗时。</summary>
    public static async Task<(bool Ok, string Error, string WavPath, double Seconds, TimeSpan Elapsed)> SynthesizeAsync(string text, string voice)
    {
        if (!Running) return (false, "服务没在运行", "", 0, TimeSpan.Zero);
        try
        {
            var payload = new Dictionary<string, object>
            {
                ["model"] = "codec-q8_0",
                ["input"] = text,
                ["response_format"] = "wav",
            };
            if (!string.IsNullOrWhiteSpace(voice)) payload["voice"] = voice;
            var body = JsonSerializer.Serialize(payload);
            var sw = Stopwatch.StartNew();
            using var c = Client();
            using var content = new StringContent(body, Encoding.UTF8, "application/json");
            var resp = await c.PostAsync($"http://127.0.0.1:{Port}/v1/audio/speech", content);
            sw.Stop();
            if (!resp.IsSuccessStatusCode)
            {
                var err = await resp.Content.ReadAsStringAsync();
                return (false, err.Length > 300 ? err.Substring(0, 300) : err, "", 0, sw.Elapsed);
            }
            var bytes = await resp.Content.ReadAsByteArrayAsync();
            var dir = Path.Combine(Path.GetTempPath(), "dsh-manager-tts");
            Directory.CreateDirectory(dir);
            var file = Path.Combine(dir, "tts-" + DateTime.Now.ToString("HHmmss") + ".wav");
            await File.WriteAllBytesAsync(file, bytes);
            double secs = 0;
            if (bytes.Length > 44)
            {
                const int rate = 24000, ch = 1, bits = 16;
                secs = (bytes.Length - 44) / (double)(rate * ch * bits / 8);
            }
            return (true, "", file, secs, sw.Elapsed);
        }
        catch (Exception ex) { return (false, "合成失败：" + ex.Message, "", 0, TimeSpan.Zero); }
    }

    private static void Append(string file, string line)
    {
        if (line == null) return;
        try { File.AppendAllText(file, line + Environment.NewLine); } catch { }
    }
}
