using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Windows.Threading;

namespace DshManager
{
    /// <summary>
    /// 轻量看门狗：UI 线程每秒 tick 一次；后台线程发现超过 8 秒没 tick，就把最近的操作面包屑写进 hang.log。
    /// 目的很单纯——**下次再卡死时，能知道卡之前用户做了什么**（拖出？保存对话框？切换开关？）。
    /// 正常运行时开销可以忽略：一个 DispatcherTimer + 一个 List。
    /// </summary>
    internal static class Watchdog
    {
        private static readonly object Gate = new object();
        private static readonly List<string> Trail = new List<string>();
        private static DateTime _lastTickUtc = DateTime.UtcNow;
        private static DateTime _lastReportUtc = DateTime.MinValue;
        private static bool _started;

        private static string LogPath => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "dsh-manager", "hang.log");

        public static void Start()
        {
            if (_started) return;
            _started = true;

            var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
            timer.Tick += (_, _) => _lastTickUtc = DateTime.UtcNow;
            timer.Start();
            _lastTickUtc = DateTime.UtcNow;

            var t = new System.Threading.Thread(() =>
            {
                while (true)
                {
                    System.Threading.Thread.Sleep(2000);
                    try
                    {
                        var gap = DateTime.UtcNow - _lastTickUtc;
                        if (gap.TotalSeconds < 8) continue;
                        if ((DateTime.UtcNow - _lastReportUtc).TotalSeconds < 10) continue;
                        _lastReportUtc = DateTime.UtcNow;
                        Report(gap);
                    }
                    catch { }
                }
            })
            { IsBackground = true, Name = "dsh-hang-watchdog" };
            t.Start();
        }

        /// <summary>记一条操作面包屑（会带上时间）。</summary>
        public static void Breadcrumb(string what)
        {
            try
            {
                lock (Gate)
                {
                    Trail.Add(DateTime.Now.ToString("HH:mm:ss.fff") + "  " + what);
                    if (Trail.Count > 24) Trail.RemoveRange(0, Trail.Count - 24);
                }
            }
            catch { }
        }

        private static void Report(TimeSpan gap)
        {
            var sb = new StringBuilder();
            sb.AppendLine("=== " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  UI 线程无响应 " + (int)gap.TotalSeconds + "s ===");
            lock (Gate)
            {
                foreach (var line in Trail) sb.AppendLine("  " + line);
            }
            sb.AppendLine();
            var dir = Path.GetDirectoryName(LogPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.AppendAllText(LogPath, sb.ToString());
        }
    }
}
