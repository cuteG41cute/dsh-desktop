using System;
using System.Collections.Generic;
using System.Text;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Threading.Tasks;
using System.Windows.Threading;
using DshManager.Services;

namespace DshManager;

public partial class App : Application
{
    private static System.Threading.Mutex _single;
    private static System.Windows.Forms.NotifyIcon _tray;
    private static System.Drawing.Icon _trayIconKeepAlive;
    private bool _quitting;

    /// <summary>真正退出（托盘菜单走这里），否则关窗口只是收进托盘。</summary>
    public void QuitForReal()
    {
        _quitting = true;
        _tray?.Dispose();
        _tray = null;
        Shutdown();
    }

    public bool Quitting => _quitting;

    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    private static extern bool AttachConsole(int pid);

    private static string LogDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "dsh-manager");

    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += (_, ex) =>
        {
            Log("unhandled: " + ex.Exception);
            ex.Handled = true;
            MessageBox.Show(ex.Exception.Message, "DeepSeek Harness 管理器");
        };
        AppDomain.CurrentDomain.UnhandledException += (_, ex) => Log("domain: " + ex.ExceptionObject);
        // 调试专用：--wizard <实例标签> 打开从备份新建向导
        var wz = Array.IndexOf(e.Args, "--wizard");
        if (wz >= 0 && wz + 1 < e.Args.Length)
        {
            var label = e.Args[wz + 1];
            var inst = Services.InstanceRegistry.Load()
                .FirstOrDefault(x => x.Label.Equals(label, StringComparison.OrdinalIgnoreCase));
            if (inst == null) { Shutdown(2); return; }
            try { Services.ThemeService.Init(); } catch { }
            RestoreWizardWindow win;
            try { win = new RestoreWizardWindow(inst); }
            catch (Exception ex)
            {
                File.WriteAllText(System.IO.Path.Combine(System.IO.Path.GetTempPath(), "wizard-error.txt"), ex.ToString());
                Shutdown(3);
                return;
            }
            var shotPath = e.Args.SkipWhile(a => a != "--shot").Skip(1).FirstOrDefault();
            win.Loaded += async (_, _) =>
            {
                await System.Threading.Tasks.Task.Delay(1200);
                if (!string.IsNullOrEmpty(shotPath))
                {
                    try
                    {
                        var w = (int)Math.Round(win.ActualWidth);
                        var h = (int)Math.Round(win.ActualHeight);
                        var rtb = new System.Windows.Media.Imaging.RenderTargetBitmap(w, h, 96, 96,
                            System.Windows.Media.PixelFormats.Pbgra32);
                        rtb.Render(win);
                        var enc = new System.Windows.Media.Imaging.PngBitmapEncoder();
                        enc.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(rtb));
                        using (var fs = File.Create(Path.GetFullPath(shotPath))) enc.Save(fs);
                    }
                    catch { }
                }
                win.Close();
                Shutdown();
            };
            win.Show();
            return;
        }

        // 调试专用：--dav-test <url> <user> <pass> <projectTitle>：上传→列目录→下载→导入（临时 home）
        var dt = Array.IndexOf(e.Args, "--dav-test");
        if (dt >= 0 && dt + 4 < e.Args.Length)
        {
            AttachConsole(-1);
            var url = e.Args[dt + 1];
            var user = e.Args[dt + 2];
            var pass = e.Args[dt + 3];
            var title = e.Args[dt + 4];
            System.Threading.Tasks.Task.Run(() =>
            {
                try
                {
                    using var dav = new Services.WebDavClient(user, pass);
                    var (ok, msg, code) = dav.TestAsync(url).GetAwaiter().GetResult();
                    Console.WriteLine($"test: ok={ok} {msg}");
                    var entry = Services.InstanceRegistry.Load().First();
                    var home = Services.ProjectCatalog.HomeFor(entry);
                    var project = Services.ProjectCatalog.ListProjects(entry, false)
                        .FirstOrDefault(p => p.Title.EndsWith(title, StringComparison.OrdinalIgnoreCase));
                    if (project == null) { Console.WriteLine("project not found: " + title); return; }
                    var tmp = Path.Combine(Path.GetTempPath(), "dav-" + Guid.NewGuid().ToString("N").Substring(0, 6) + ".dshproj");
                    var exp = Services.ProjectMigration.Export(
                        new Services.ProjectMigration.ProjectInfo(project.Id, project.Path, project.Title, project.Sessions),
                        tmp, true, Console.WriteLine, home);
                    Console.WriteLine("export: " + exp.Ok + " " + exp.Message);
                    if (!exp.Ok) return;
                    var remoteDir = url.TrimEnd('/') + "/dsh-backup/test-device";
                    var mk = dav.EnsureCollectionAsync(remoteDir).GetAwaiter().GetResult();
                    Console.WriteLine("mkcol: " + mk.Ok + " " + mk.Message);
                    var remoteFile = remoteDir + "/" + Path.GetFileName(tmp);
                    dav.UploadAsync(tmp, remoteFile).GetAwaiter().GetResult();
                    Console.WriteLine("upload ok: " + remoteFile + " (" + new FileInfo(tmp).Length + " B)");
                    var list = dav.ListAsync(remoteDir).GetAwaiter().GetResult();
                    Console.WriteLine("list: " + string.Join(", ", list.Select(x => x.Name + "(" + x.Size + ")")));
                    var back = Path.Combine(Path.GetTempPath(), "dav-back-" + Guid.NewGuid().ToString("N").Substring(0, 6) + ".dshproj");
                    dav.DownloadAsync(remoteFile, back).GetAwaiter().GetResult();
                    Console.WriteLine("download: " + new FileInfo(back).Length + " B");
                    var tempHome = Path.Combine(Path.GetTempPath(), "dav-home-" + Guid.NewGuid().ToString("N").Substring(0, 6));
                    Directory.CreateDirectory(Path.Combine(tempHome, "storages"));
                    Directory.CreateDirectory(Path.Combine(tempHome, "sessions"));
                    var dest = Path.Combine(Path.GetTempPath(), "dav-dest-" + Guid.NewGuid().ToString("N").Substring(0, 6));
                    var imp = Services.ProjectMigration.Import(back, dest, Console.WriteLine, tempHome);
                    Console.WriteLine("import: " + imp.Ok + " " + imp.Message);
                    var ws = Path.Combine(tempHome, "storages", "workspace.json");
                    Console.WriteLine("workspace exists: " + File.Exists(ws));
                    try { File.Delete(tmp); File.Delete(back); } catch { }
                }
                catch (Exception ex) { Console.WriteLine("dav-test failed: " + ex); }
            }).Wait(TimeSpan.FromMinutes(5));
            Shutdown(0);
            return;
        }

        // 提权助手：--fence-exempt <profileName>（由 UAC 拉起，做 AppContainer 回环豁免）
        var fx = Array.IndexOf(e.Args, "--fence-exempt");
        if (fx >= 0 && fx + 1 < e.Args.Length)
        {
            var profile = e.Args[fx + 1];
            var r = Services.AppContainerFence.TryLoopbackExempt(profile);
            try
            {
                System.IO.File.WriteAllText(System.IO.Path.Combine(System.IO.Path.GetTempPath(),
                    "dsh-fence-exempt-" + profile + ".txt"),
                    (r.Ok ? "OK" : "FAIL") + "\n" + r.Message);
            }
            catch { }
            Shutdown(r.Ok ? 0 : 1);
            return;
        }

        // 调试/自动化：--install-instance <dir> <port> <system|user>
        var ii = Array.IndexOf(e.Args, "--install-instance");
        if (ii >= 0 && ii + 3 < e.Args.Length)
        {
            try { System.IO.File.WriteAllText(@"C:\\dshbuild\\cli-start.log", string.Join("|", e.Args)); } catch { }
            try
            {
            AttachConsole(-1);
            var dir = e.Args[ii + 1];
            var port = int.Parse(e.Args[ii + 2]);
            var tier = e.Args[ii + 3];
            var logLines = new System.Collections.Concurrent.ConcurrentQueue<string>();
            // WPF 启动线程上有同步上下文，直接 .GetResult() 会死锁；放到线程池跑
            var (iok, imsg) = System.Threading.Tasks.Task.Run(() =>
                Services.InstanceInstaller.InstallAsync(dir, "latest",
                    m => logLines.Enqueue(m), port, "latest")).GetAwaiter().GetResult();
            try
            {
                System.IO.Directory.CreateDirectory(dir);
                System.IO.File.WriteAllText(System.IO.Path.Combine(dir, "install-cli.log"),
                    string.Join("\n", logLines) + "\nRESULT: " + iok + " " + imsg + "\n");
            }
            catch { }
            if (iok)
            {
                var entry = new Services.RegistryEntry
                {
                    Id = "inst-" + Guid.NewGuid().ToString("N").Substring(0, 8),
                    Label = Path.GetFileName(dir.TrimEnd('\\')),
                    Dir = dir, Port = port,
                    Tier = tier == "user" ? "user" : "system",
                    FenceRoot = tier == "user" ? dir : "",
                    CreatedAt = DateTime.Now.ToString("o"),
                };
                Services.InstanceRegistry.Add(entry);
            }
            Console.WriteLine("install=" + iok + " " + imsg);
            Shutdown(iok ? 0 : 1);
            return;
            }
            catch (Exception ex)
            {
                try { System.IO.File.WriteAllText(@"C:\\dshbuild\\cli-error.log", ex.ToString()); } catch { }
                Shutdown(3);
                return;
            }
        }

        // 调试/自动化：--fence-create <label> <name>
        var fc = Array.IndexOf(e.Args, "--fence-create");
        if (fc >= 0 && fc + 2 < e.Args.Length)
        {
            AttachConsole(-1);
            var label = e.Args[fc + 1];
            var name = e.Args[fc + 2];
            var list = Services.DshDiscovery.Scan().ToList();
            Services.DshDiscovery.AttachRunning(list);
            Services.DshDiscovery.ApplyRegistryPorts(list);
            var inst = list.FirstOrDefault(i => i.Label.Equals(label, StringComparison.OrdinalIgnoreCase));
            if (inst == null) { Console.WriteLine("instance not found: " + label); Shutdown(2); return; }
            var (fok, fmsg) = Services.FenceWorkspace.CreateAsync(inst, name).GetAwaiter().GetResult();
            Console.WriteLine("fence-create=" + fok + " " + fmsg);
            Shutdown(fok ? 0 : 1);
            return;
        }

        // 调试专用：--ac-debug <label> <commandLine> [env|noenv]
        var ac = Array.IndexOf(e.Args, "--ac-debug");
        if (ac >= 0 && ac + 2 < e.Args.Length)
        {
            AttachConsole(-1);
            var label = e.Args[ac + 1];
            var cmd = e.Args[ac + 2];
            var useEnv = ac + 3 >= e.Args.Length || e.Args[ac + 3] != "noenv";
            var inst = Services.DshDiscovery.Scan().FirstOrDefault(x =>
                x.Label.Equals(label, StringComparison.OrdinalIgnoreCase));
            var reg = Services.InstanceRegistry.Load().FirstOrDefault(r =>
                r.Label.Equals(label, StringComparison.OrdinalIgnoreCase));
            if (inst == null || reg == null) { Console.WriteLine("instance not found"); Shutdown(2); return; }
            var fence = string.IsNullOrWhiteSpace(reg.FenceRoot) ? inst.Dir : reg.FenceRoot;
            var profile = Services.AppContainerFence.ProfileNameFor(inst.Id);
            var en = Services.AppContainerFence.EnsureProfile(profile);
            Console.WriteLine("profile " + en.Ok + " " + en.Sid);
            var gr = Services.AppContainerFence.GrantDirectory(fence, en.Sid);
            Console.WriteLine("grant " + gr.Ok + " " + gr.Message);
            string envBlock = null;
            if (useEnv)
            {
                var tmp = Path.Combine(fence, "tmp");
                Directory.CreateDirectory(tmp);
                var env = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
                {
                    ["SystemRoot"] = Environment.GetEnvironmentVariable("SystemRoot") ?? "C:\\Windows",
                    ["windir"] = Environment.GetEnvironmentVariable("windir") ?? "C:\\Windows",
                    ["SystemDrive"] = Environment.GetEnvironmentVariable("SystemDrive") ?? "C:",
                    ["ComSpec"] = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe"),
                    ["PATH"] = Environment.GetFolderPath(Environment.SpecialFolder.System),
                    ["TEMP"] = tmp, ["TMP"] = tmp,
                    ["USERPROFILE"] = fence, ["HOME"] = fence,
                    ["DSH_HOME"] = inst.Home,
                    ["DSH_FENCE_ROOT"] = fence,
                    ["DSH_PERMISSION_MODE"] = "workspace-write",
                };
                var sb = new StringBuilder();
                foreach (var kv in env) sb.Append(kv.Key).Append('=').Append(kv.Value).Append('\0');
                sb.Append('\0');
                envBlock = sb.ToString();
            }
            var r = Services.AppContainerFence.Start(profile, cmd, fence, true, envBlock, IntPtr.Zero);
            Console.WriteLine($"start={r.Ok} pid={r.Pid} {r.Message}");
            Shutdown(r.Ok ? 0 : 1);
            return;
        }

        // 调试专用：--set-tier <label> <system|user>：设置实例等级
        var st = Array.IndexOf(e.Args, "--set-tier");
        if (st >= 0 && st + 2 < e.Args.Length)
        {
            AttachConsole(-1);
            var label = e.Args[st + 1];
            var tier = e.Args[st + 2].ToLowerInvariant();
            var reg = Services.InstanceRegistry.Load()
                .FirstOrDefault(r => r.Label.Equals(label, StringComparison.OrdinalIgnoreCase));
            if (reg == null) { Console.WriteLine("instance not found: " + label); Shutdown(2); return; }
            reg.Tier = tier == "user" ? "user" : "system";
            reg.FenceRoot = tier == "user" ? reg.Dir : "";
            Services.InstanceRegistry.Add(reg);
            Console.WriteLine($"tier={reg.Tier} fence={reg.FenceRoot}");
            Shutdown(0);
            return;
        }

        // 调试专用：--instance-start <label>：按管理器逻辑启动实例
        var si = Array.IndexOf(e.Args, "--instance-start");
        if (si >= 0 && si + 1 < e.Args.Length)
        {
            void Trace(string m) { try { System.IO.File.AppendAllText(@"C:\\dshbuild\\is-start.log", DateTime.Now.ToString("HH:mm:ss") + " " + m + "\n"); } catch { } }
            Trace("args: " + string.Join("|", e.Args));
            try
            {
            AttachConsole(-1);
            var label = e.Args[si + 1];
            var list = Services.DshDiscovery.Scan().ToList();
            Services.DshDiscovery.AttachRunning(list);
            Services.DshDiscovery.ApplyRegistryPorts(list);
            var inst = list.FirstOrDefault(i => i.Label.Equals(label, StringComparison.OrdinalIgnoreCase));
            if (inst == null) { Console.WriteLine("instance not found: " + label); Shutdown(2); return; }
            Trace("found inst=" + inst.Label + " dir=" + inst.Dir + " node=" + inst.NodeExe + " entry=" + inst.Entry + " port=" + inst.Port);
            var ok = Services.DshHost.Start(inst, out var msg);
            Trace("start=" + ok + " " + msg + " port=" + inst.Port);
            Console.WriteLine("start=" + ok + " " + msg + " port=" + inst.Port);
            Shutdown(ok ? 0 : 1);
            return;
            }
            catch (Exception ex)
            {
                Trace("EX: " + ex);
                Shutdown(4);
                return;
            }
        }

        // 调试专用：--storage-check [home] / --storage-repair [home]
        var sc = Array.IndexOf(e.Args, "--storage-check");
        var sr = Array.IndexOf(e.Args, "--storage-repair");
        if (sc >= 0 || sr >= 0)
        {
            AttachConsole(-1);
            var home = e.Args.SkipWhile(a => a != (sc >= 0 ? "--storage-check" : "--storage-repair")).Skip(1)
                .FirstOrDefault() ?? Services.ProjectCatalog.HomeFor(
                    Services.InstanceRegistry.Load().FirstOrDefault() ?? new Services.RegistryEntry());
            if (!Directory.Exists(Path.Combine(home, "storages")))
                home = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".dsh");
            Console.WriteLine("home: " + home);
            foreach (var r in Services.StorageHealth.Check(home))
            {
                Console.WriteLine($"  {Path.GetFileName(r.Path)}  bom={r.HasBom} parses={r.Parses}  {r.Message}");
                if (sr >= 0 && r.HasBom)
                {
                    var (ok, msg) = Services.StorageHealth.RepairBom(r.Path);
                    Console.WriteLine("    repair: " + msg);
                }
            }
            Shutdown(0);
            return;
        }

        // 调试专用：--backup-run <实例标签>
        var br = Array.IndexOf(e.Args, "--backup-run");
        if (br >= 0 && br + 1 < e.Args.Length)
        {
            AttachConsole(-1);
            var label = e.Args[br + 1];
            var inst = Services.InstanceRegistry.Load()
                .FirstOrDefault(x => x.Label.Equals(label, StringComparison.OrdinalIgnoreCase));
            if (inst == null) { Console.WriteLine("instance not found: " + label); Shutdown(2); return; }
            var plan = Services.BackupPlanStore.Load(inst.Id);
            if (string.IsNullOrWhiteSpace(plan.Directory))
                plan.Directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "dsh-backup");
            var projects = Services.ProjectCatalog.ListProjects(inst, false);
            var result = Services.BackupRunner.Run(inst, plan, projects, Console.WriteLine);
            Console.WriteLine($"ok={result.Ok} failed={result.Failed}");
            foreach (var m in result.Messages) Console.WriteLine("  " + m);
            Shutdown(0);
            return;
        }

        // 调试专用：--list-projects [实例标签|all]
        var lp = Array.IndexOf(e.Args, "--list-projects");
        if (lp >= 0)
        {
            AttachConsole(-1);
            var want = lp + 1 < e.Args.Length ? e.Args[lp + 1] : "all";
            var entries = Services.InstanceRegistry.Load();
            foreach (var inst in entries)
            {
                if (want != "all" && !inst.Label.Equals(want, StringComparison.OrdinalIgnoreCase)) continue;
                var home = Services.ProjectCatalog.HomeFor(inst);
                Console.WriteLine($"== {inst.Label} :{inst.Port} home={home}");
                foreach (var p in Services.ProjectCatalog.ListProjects(inst))
                {
                    var act = p.LastActivity?.ToString("MM-dd HH:mm") ?? "-";
                    var bak = p.LastBackupAt?.ToString("MM-dd HH:mm") ?? "-";
                    Console.WriteLine($"   {p.Title} | {p.Sessions} 会话 | {p.SizeBytes / 1024 / 1024} MB | 活动 {act} | 备份 {p.BackupState} {bak} {p.BackupLocation} | handoff={p.HasHandoff}");
                }
            }
            Shutdown(0);
            return;
        }

        // 调试专用：--migrate-export <标题片段> <out.dshproj> / --migrate-import <包> <目标目录>
        var mi = Array.IndexOf(e.Args, "--migrate-export");
        if (mi >= 0 && mi + 2 < e.Args.Length)
        {
            AttachConsole(-1);
            var needle = e.Args[mi + 1];
            var outFile = e.Args[mi + 2];
            var p = Services.ProjectMigration.ListProjects()
                .FirstOrDefault(x => x.Title.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0);
            if (p == null) { Console.WriteLine("project not found: " + needle); Shutdown(2); return; }
            var (ok, msg) = Services.ProjectMigration.Export(p, outFile, true, Console.WriteLine);
            Console.WriteLine("ok=" + ok + " msg=" + msg);
            Shutdown(ok ? 0 : 1);
            return;
        }
        var mj = Array.IndexOf(e.Args, "--migrate-import");
        if (mj >= 0 && mj + 2 < e.Args.Length)
        {
            AttachConsole(-1);
            var (ok, msg) = Services.ProjectMigration.Import(e.Args[mj + 1], e.Args[mj + 2], Console.WriteLine);
            Console.WriteLine("ok=" + ok + " msg=" + msg);
            Shutdown(ok ? 0 : 1);
            return;
        }

        // 调试专用：--tts-addvoice <名字> <wav路径> 测试音色写入
        var ai = Array.IndexOf(e.Args, "--tts-addvoice");
        if (ai >= 0 && ai + 2 < e.Args.Length)
        {
            AttachConsole(-1);
            var vname = e.Args[ai + 1];
            var vwav = e.Args[ai + 2];
            var resv = Services.AudioCppService.AddVoice(vname, vwav, "测试参考文本");
            Console.WriteLine("ok=" + resv.Ok + " msg=" + resv.Message);
            Shutdown(resv.Ok ? 0 : 1);
            return;
        }

        // 调试专用：--tts-download <模型id> 直接用管理器自己的下载器拉模型，进度打到控制台
        var dlArgs = e.Args;
        var di = Array.IndexOf(dlArgs, "--tts-download");
        if (di >= 0 && di + 1 < dlArgs.Length)
        {
            AttachConsole(-1);
            var id = dlArgs[di + 1];
            var model = Array.Find(Services.AudioCppService.Models, m => m.Id == id);
            if (model == null)
            {
                Console.WriteLine("unknown model: " + id);
                Console.WriteLine("available: " + string.Join(",", Array.ConvertAll(Services.AudioCppService.Models, m => m.Id)));
                Shutdown(2);
                return;
            }
            Console.WriteLine("downloading " + model.Id + " -> " + Services.AudioCppService.ModelPath(model));
            var sw = System.Diagnostics.Stopwatch.StartNew();
            // 注意：不能在 UI 线程上直接 .GetAwaiter().GetResult()，否则第一个 await
            // 之后的续体会排到 Dispatcher 上而 Dispatcher 还没开始跑 → 死锁（表现为「下载卡在 0%」）。
            var res = System.Threading.Tasks.Task.Run(() => Services.AudioCppService.DownloadModelAsync(model, (done, total, name) =>
            {
                var pct = total > 0 ? (int)(done * 100.0 / total) : 0;
                Console.WriteLine($"{sw.Elapsed.TotalSeconds,7:F1}s  {done / 1048576,6} MB / {total / 1048576,6} MB  {pct,3}%");
            })).GetAwaiter().GetResult();
            Console.WriteLine("ok=" + res.Item1 + " msg=" + res.Item2);
            Shutdown(res.Item1 ? 0 : 1);
            return;
        }
        try
        {
            // ---- 单实例：已经有管理器在跑就把它提到前台，然后退出本次 ----
            _single = new System.Threading.Mutex(true, "Global\\DshManager", out var isNew);
            if (!isNew)
            {
                var other = System.Diagnostics.Process.GetProcessesByName("DshManager")
                    .FirstOrDefault(p => p.Id != System.Diagnostics.Process.GetCurrentProcess().Id);
                if (other != null)
                {
                    // 已经有管理器在跑：把它的窗口弄出来。
                    // 点过 X 收进托盘时窗口是**隐藏**的，MainWindowHandle 会返回 0，
                    // 只看它就会「什么都没发生」——用户看到的就是「程序启动不了」。
                    var hwnd = other.MainWindowHandle;
                    if (hwnd == IntPtr.Zero) hwnd = FindManagerWindow(other.Id);
                    if (hwnd != IntPtr.Zero)
                    {
                        ShowWindow(hwnd, 9);          // SW_RESTORE
                        ShowWindow(hwnd, 5);          // SW_SHOW（托盘隐藏后必须显式显示）
                        SetForegroundWindow(hwnd);
                        SetWindowPos(hwnd, new IntPtr(-1), 0, 0, 0, 0, 0x0003); // 顶一下
                        SetWindowPos(hwnd, new IntPtr(-2), 0, 0, 0, 0, 0x0003); // 再取消置顶
                    }
                }
                Shutdown();
                return;
            }

            // 安装包里内嵌的 audio.cpp 运行时（带 eSpeak）——首次启动释放出来
            System.Threading.Tasks.Task.Run(() =>
            {
                Services.AudioCppService.EnsureBundledRuntime();
                Services.AudioCppService.EnsureBundledVoice();
            });

            base.OnStartup(e);
            // WPF 的 UI 线程异常默认会**直接结束进程**，而且不走 AppDomain 处理器 →
            // 之前「点停止，管理器自己没了」就是这条通道，崩溃日志里一个字都没有。
            // 现在：记日志 + 保持运行，界面里给出提示，不再静默退出。
            try
            {
                DispatcherUnhandledException += (_, ev) =>
                {
                    // 只记日志、不弹窗、不退出：界面错误不该干扰用户，也不该带走进程。
                    Log("ui-dispatcher: " + ev.Exception);
                    ev.Handled = true;
                };
            }
            catch { }

            // 兜底诊断：托盘/UI 线程上的异常与未观测的 Task 异常也要进 crash.log，
            // 否则进程静默退出时完全无法排查。
            try
            {
                System.Windows.Forms.Application.ThreadException +=
                    (_, ev) => Log("ui-thread: " + ev.Exception);
                System.Threading.Tasks.TaskScheduler.UnobservedTaskException += (_, ev) =>
                {
                    // 端口探测的 TcpClient 被取消会抛 SocketException(995)，纯噪音
                    if (ev.Exception.ToString().Contains("995") || ev.Exception.ToString().Contains("SocketException")) return;
                    Log("unobserved-task: " + ev.Exception);
                };
            }
            catch { }

            ThemeService.Init();
            CreateTray();

            // --shot <png> [--theme frost --mode day]：把窗口按 96dpi 渲染成 PNG 后退出。
            // 走 RenderTargetBitmap 而不是屏幕截图：本机是 200% 缩放，屏幕截图要么拿到
            // 半个窗口放大、要么拿到垃圾矩形；离屏渲染得到的就是 1280×812 的 DIP 像素，
            // 正好和设计稿（1 CSS px = 1 DIP）逐像素比对。
            var args = Environment.GetCommandLineArgs();
            // --open [--open-hold 秒]：按当前发现的实例打开内置会话窗，到时自动退出（自检用）。
            // 单独用，不用配 --shot：会话窗里是 WebView2 原生子窗口，离屏渲染拍不到。
            if (args.Contains("--open"))
            {
                var hold = args.SkipWhile(a => a != "--open-hold").Skip(1).FirstOrDefault();
                OpenWindowSelfCheck(int.TryParse(hold, out var holdSeconds) ? holdSeconds : 10);
                return;
            }
            // --selftest-install <dir>：真装一份实例，然后依次跑 修复/更新/卸载，结果写 crash.log。
            // 用来在没有界面的情况下走一遍「管理器创建的实例」的完整生命周期。
            if (args.Contains("--selftest-install"))
            {
                var dir = args.SkipWhile(a => a != "--selftest-install").Skip(1).FirstOrDefault();
                SelfTestInstallAndExit(dir ?? "");
                return;
            }
            // --selftest-source <dir> [--ref master]：走「源码检出」安装路径（与新建实例的
            // 「安装方式·官方仓库源码」完全同一条代码），用来在没有界面的情况下验证 clone/pnpm 链路。
            if (args.Contains("--selftest-source"))
            {
                var dir = args.SkipWhile(a => a != "--selftest-source").Skip(1).FirstOrDefault() ?? "";
                var gitRef = args.SkipWhile(a => a != "--ref").Skip(1).FirstOrDefault() ?? "master";
                SelfTestSourceAndExit(dir, gitRef);
                return;
            }
            if (args.Contains("--shot"))
{
                var path = args.SkipWhile(a => a != "--shot").Skip(1).FirstOrDefault()
                           ?? "shot.png";
                var theme = args.SkipWhile(a => a != "--theme").Skip(1).FirstOrDefault();
                var mode = args.SkipWhile(a => a != "--mode").Skip(1).FirstOrDefault();
                var size = args.SkipWhile(a => a != "--size").Skip(1).FirstOrDefault();
                if (!string.IsNullOrEmpty(theme)) ThemeService.SetTheme(theme);
                if (!string.IsNullOrEmpty(mode) && mode != ThemeService.Mode) ThemeService.ToggleMode();
                if (args.Contains("--selftest-actions"))
                {
                    SelfTestActionsAndExit();
                }
                else if (args.Contains("--newinstance"))
                {
                    NewInstanceShotAndExit(path);
                }
                else if (args.Contains("--plugins"))
                {
                    PluginsShotAndExit(path);
                }
                else
                {
                    ShotAndExit(path, size);
                }
                return;
            }

            // 正常启动：管理器主窗口。README 里的 StartupUri 已经去掉，
            // 命令行模式（--open/--shot/…）就不会顺带弹一个管理器窗口出来。
            var main = new MainWindow();
            main.Show();
        }
        catch (Exception ex)
        {
            Log("startup: " + ex);
            throw;
        }
    }

    /// <summary>
    /// --selftest-install &lt;dir&gt;：装一份实例，然后依次跑 修复 / 更新 / 卸载。
    /// 结果写进 crash.log（开发期验证「管理器创建的实例」这套动作，不用点界面）。
    /// </summary>
    /// <summary>
    /// 源码安装自检：直接调用 InstanceInstaller.InstallSourceAsync（与新建实例同一条路径），
    /// 日志写进 %LOCALAPPDATA%/dsh-manager/source-test.log，便于边跑边看。
    /// </summary>
    private void SelfTestSourceAndExit(string dir, string gitRef)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var logPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "dsh-manager", "source-test.log");
        Directory.CreateDirectory(Path.GetDirectoryName(logPath) ?? ".");
        void Slog(string m)
        {
            try { File.AppendAllText(logPath, DateTime.Now.ToString("HH:mm:ss.fff ") + m + Environment.NewLine); } catch { }
        }

        Task.Run(async () =>
        {
            try
            {
                Slog("[source-test] dir=" + dir + " ref=" + gitRef);
                var (ok, msg) = await InstanceInstaller.InstallSourceAsync(dir, "latest", m => Slog("    | " + m), 0, gitRef);
                Slog("[source-test] result -> " + (ok ? "OK" : "FAIL") + ": " + msg);
            }
            catch (Exception ex)
            {
                Slog("[source-test] exception: " + ex);
            }
            finally
            {
                Dispatcher.Invoke(() => Shutdown());
            }
        });
    }

    private void SelfTestInstallAndExit(string dir)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        Task.Run(async () =>
        {
            try
            {
                if (string.IsNullOrWhiteSpace(dir))
                {
                    dir = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "dsh-manager", "instances", "selftest");
                    Log("[install-test] 没给目录，用默认：" + dir);
                }
                Log("[install-test] dir=" + dir);
                var binJs = Path.Combine(dir, "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js");
                if (File.Exists(binJs))
                {
                    Log("[install-test] 目录里已经有安装，跳过 npm install");
                }
                else
                {
                    var (iok, imsg) = await InstanceInstaller.InstallAsync(
                        dir, "latest", m => Log("    npm | " + m), 0);
                    Log("[install-test] install -> " + (iok ? "OK" : "FAIL") + ": " + imsg);
                    if (!iok) return;
                }

                var list = DshDiscovery.Scan().ToList();
                DshDiscovery.AttachRunning(list);
                var inst = list.FirstOrDefault(i => string.Equals(
                    Path.GetFullPath(i.Dir ?? ""), Path.GetFullPath(dir), StringComparison.OrdinalIgnoreCase));
                if (inst == null)
                {
                    Log("[install-test] 扫描没找到这个实例（发现 " + list.Count + " 个）");
                    foreach (var i in list) Log("[install-test]   saw " + i.Label + " dir=" + i.Dir);
                    return;
                }
                Log("[install-test] found " + inst.Label + " ver=" + inst.DshVersion
                    + " managed=" + InstanceActions.IsManaged(inst) + " entry=" + inst.Entry);

                var (rok, rmsg) = await InstanceActions.RepairAsync(inst, m => Log("    repair | " + m));
                Log("[install-test] repair -> " + (rok ? "OK" : "FAIL") + ": " + rmsg);

                var (uok, umsg) = await InstanceActions.UpdateAsync(inst, m => Log("    update | " + m));
                Log("[install-test] update -> " + (uok ? "OK" : "FAIL") + ": " + umsg);

                var (dok, dmsg) = InstanceActions.Uninstall(inst, deleteDir: true);
                Log("[install-test] uninstall -> " + (dok ? "OK" : "FAIL") + ": " + dmsg);
            }
            catch (Exception ex)
            {
                Log("[install-test] 异常：" + ex);
            }
            finally
            {
                Dispatcher.Invoke(Shutdown);
            }
        });
    }

    private void ShotAndExit(string path, string size)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var win = new MainWindow();
        if (!string.IsNullOrEmpty(size))
        {
            var parts = size.Split('x');
            if (parts.Length == 2 && double.TryParse(parts[0], out var sw) &&
                double.TryParse(parts[1], out var sh))
            {
                win.Width = sw;
                win.Height = sh;
            }
        }
        win.Show();
        if (Environment.GetCommandLineArgs().Contains("--page"))
        {
            var page = Environment.GetCommandLineArgs().SkipWhile(a => a != "--page").Skip(1).FirstOrDefault() ?? "";
            if (page == "settings") win.OpenSettingsPage();
            else if (page == "tts") win.OpenTtsPage();
            if (Environment.GetCommandLineArgs().Contains("--expand"))
            {
                var which = Environment.GetCommandLineArgs().SkipWhile(a => a != "--expand").Skip(1).FirstOrDefault();
                if (which == "pb") win.ExpandProjectCard();
                else if (which == "voice") win.ExpandVoiceCard();
                var modal = Environment.GetCommandLineArgs().SkipWhile(a => a != "--modal").Skip(1).FirstOrDefault();
                if (modal == "export") win.OpenFirstProjectExport();
                else if (modal == "import") win.OpenImportModal();
                else if (modal == "backup") win.OpenBackupTabForShot();
                else if (modal == "handoff") win.OpenHandoffFirst();
            }
        }
        var delayMs = Environment.GetCommandLineArgs().Contains("--modal") ? 2600 : 900;
        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(delayMs) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            try
            {
                var w = (int)Math.Round(win.ActualWidth);
                var h = (int)Math.Round(win.ActualHeight);
                var rtb = new RenderTargetBitmap(w, h, 96, 96, PixelFormats.Pbgra32);
                rtb.Render(win);
                var enc = new PngBitmapEncoder();
                enc.Frames.Add(BitmapFrame.Create(rtb));
                using (var fs = File.Create(Path.GetFullPath(path)))
                    enc.Save(fs);
                Log($"shot -> {Path.GetFullPath(path)} ({w}x{h})");
            }
            catch (Exception ex)
            {
                Log("shot failed: " + ex);
            }
            win.Close();
            Shutdown();
        };
        timer.Start();
    }

    /// <summary>--plugins：只打开插件对话框并截图（开发期用来核对样式/数据）。</summary>
    /// <summary>--open [--open-hold 秒]：按当前发现的实例打开内置会话窗（自检用），到时退出。</summary>
    private void OpenWindowSelfCheck(int holdSeconds = 10)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var list = DshDiscovery.Scan().ToList();
        DshDiscovery.AttachRunning(list);
        DshDiscovery.ApplyRegistryPorts(list);
        var inst = list.FirstOrDefault(i => i.Running) ?? list.FirstOrDefault();
        if (inst == null) { Log("[open] 没有可用实例"); Shutdown(); return; }
        var ok = DshHost.OpenWindow(inst, out var msg);
        Log("[open] " + inst.Label + " port=" + inst.Port + " -> " + (ok ? "OK" : "FAIL") + ": " + msg);
        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(Math.Max(2, holdSeconds)) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            Log("[open] titles=" + string.Join(" | ",
                System.Windows.Application.Current.Windows.Cast<Window>().Select(w => w.Title)));
            Shutdown();
        };
        timer.Start();
    }

    /// <summary>
    /// --selftest-actions：对发现的每个实例跑一遍「是否受管 / 修复自检」，
    /// 结果写进 crash.log（开发期用命令行验证动作层，不用点界面）。
    /// </summary>
    private void SelfTestActionsAndExit()
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        Task.Run(async () =>
        {
            var list = DshDiscovery.Scan().ToList();
            DshDiscovery.AttachRunning(list);
            DshDiscovery.ApplyRegistryPorts(list);
            foreach (var inst in list)
            {
                Log("[selftest] " + inst.Label + " | " + inst.Source + " | dir=" + inst.Dir
                    + " | managed=" + InstanceActions.IsManaged(inst)
                    + " | running=" + inst.Running + " port=" + inst.Port);
                var (ok, msg) = await InstanceActions.RepairAsync(inst, m => Log("    | " + m));
                Log("[selftest]   repair -> " + (ok ? "OK" : "FAIL") + ": " + msg);
            }
            Dispatcher.Invoke(Shutdown);
        });
    }

    /// <summary>--newinstance：只打开「新建实例」对话框并截图。</summary>
    private void NewInstanceShotAndExit(string path)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var win = new NewInstanceWindow();
        win.Show();
        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(900) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            try
            {
                var w = (int)Math.Round(win.ActualWidth);
                var h = (int)Math.Round(win.ActualHeight);
                var rtb = new RenderTargetBitmap(Math.Max(w, 1), Math.Max(h, 1), 96, 96, PixelFormats.Pbgra32);
                rtb.Render(win);
                var enc = new PngBitmapEncoder();
                enc.Frames.Add(BitmapFrame.Create(rtb));
                using (var fs = File.Create(Path.GetFullPath(path))) enc.Save(fs);
                Log($"newinstance shot -> {Path.GetFullPath(path)} ({w}x{h})");
            }
            catch (Exception ex) { Log("newinstance shot failed: " + ex); }
            win.Close();
            Shutdown();
        };
        timer.Start();
    }

    private void PluginsShotAndExit(string path)
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var list = DshDiscovery.Scan().ToList();
        DshDiscovery.AttachRunning(list);
        var inst = list.FirstOrDefault();
        if (inst == null) { Log("no instance for plugins shot"); Shutdown(); return; }
        var win = new PluginWindow(inst);
        win.Show();
        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(5) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            try
            {
                var w = (int)Math.Round(win.ActualWidth);
                var h = (int)Math.Round(win.ActualHeight);
                var rtb = new RenderTargetBitmap(Math.Max(w, 1), Math.Max(h, 1), 96, 96, PixelFormats.Pbgra32);
                rtb.Render(win);
                var enc = new PngBitmapEncoder();
                enc.Frames.Add(BitmapFrame.Create(rtb));
                using (var fs = File.Create(Path.GetFullPath(path))) enc.Save(fs);
                Log($"plugins shot -> {Path.GetFullPath(path)} ({w}x{h})");
            }
            catch (Exception ex) { Log("plugins shot failed: " + ex); }
            win.Close();
            Shutdown();
        };
        timer.Start();
    }


    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int n);

    // ---------------------------------------------------------------- 找已运行实例的窗口
    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern int GetWindowTextW(IntPtr hWnd, System.Text.StringBuilder text, int max);

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern int GetClassNameW(IntPtr hWnd, System.Text.StringBuilder text, int max);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

    /// <summary>
    /// 在指定进程的所有顶层窗口里找管理器主窗口（托盘隐藏时也能找到）：
    /// 优先标题里带「管理器」的，其次任意有标题的 DshManager 窗口。
    /// </summary>
    private static IntPtr FindManagerWindow(int pid)
    {
        IntPtr fallback = IntPtr.Zero;
        EnumWindows((h, _) =>
        {
            uint owner;
            GetWindowThreadProcessId(h, out owner);
            if (owner != (uint)pid) return true;
            var cls = new System.Text.StringBuilder(256);
            GetClassNameW(h, cls, 256);
            if (cls.ToString().IndexOf("DshManager", StringComparison.OrdinalIgnoreCase) < 0) return true;
            var text = new System.Text.StringBuilder(512);
            GetWindowTextW(h, text, 512);
            var title = text.ToString();
            if (title.Contains("管理器"))
            {
                fallback = h;
                return false;            // 找到主窗口，停
            }
            if (fallback == IntPtr.Zero && !string.IsNullOrWhiteSpace(title)) fallback = h;
            return true;
        }, IntPtr.Zero);
        return fallback;
    }

    /// <summary>
    /// 托盘图标：优先取 exe 里嵌入的应用图标（128/256 那档缩到 32 才清楚）。
    /// 取不到就退回系统默认图标，绝不因为图标缺失而起不来。
    /// </summary>
    private static System.Drawing.Icon TrayIconOf()
    {
        try
        {
            var exe = System.Diagnostics.Process.GetCurrentProcess().MainModule?.FileName;
            if (!string.IsNullOrEmpty(exe))
            {
                var small = System.Drawing.Icon.ExtractAssociatedIcon(exe);
                if (small != null)
                {
                    // 用 Icon(icon, size) 复制一份：新 Icon **自己拥有** 句柄，
                    // 不会因为临时 Bitmap 被 GC 而让托盘拿到失效 HICON（那是会崩进程的）。
                    var scaled = new System.Drawing.Icon(small, 32, 32);
                    _trayIconKeepAlive = scaled;
                    return scaled;
                }
            }
        }
        catch { }
        return System.Drawing.SystemIcons.Application;
    }

    private void CreateTray()
    {
        try
        {
            _tray = new System.Windows.Forms.NotifyIcon
            {
                // 托盘图标用 exe 自己的图标（黑鲸鱼），别用系统的默认程序图标
            Icon = TrayIconOf(),
                Text = "DeepSeek Harness 管理器",
                Visible = true,
            };
            var menu = new System.Windows.Forms.ContextMenuStrip();
            menu.Items.Add("显示管理器", null, (_, _) => ShowMain());
            menu.Items.Add("退出", null, (_, _) => QuitForReal());
            _tray.ContextMenuStrip = menu;
            _tray.DoubleClick += (_, _) => ShowMain();
        }
        catch { _tray = null; }
    }

    private void ShowMain()
    {
        foreach (Window w in Windows)
        {
            if (w is MainWindow mw)
            {
                mw.Show();
                if (mw.WindowState == WindowState.Minimized) mw.WindowState = WindowState.Normal;
                mw.Activate();
                return;
            }
        }
    }

    public static void DebugLog(string text) => Log(text);

    private static void Log(string text)
    {
        try
        {
            Directory.CreateDirectory(LogDir);
            File.AppendAllText(Path.Combine(LogDir, "crash.log"),
                DateTime.Now.ToString("HH:mm:ss ") + text + Environment.NewLine);
        }
        catch { }
    }
}
