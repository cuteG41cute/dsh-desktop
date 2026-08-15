// DSH Desktop - a thin WebView2 wrapper that embeds the DeepSeek Harness WebUI
// in a native window instead of a browser tab.
//
// Build (no .NET SDK needed; uses the .NET Framework C# compiler that ships
// with Windows):
//   csc.exe /nologo /target:winexe /platform:x64 /optimize+ \
//     /out:"DSH Desktop.exe" /win32icon:app.ico \
//     /r:System.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll \
//     /r:Microsoft.Web.WebView2.Core.dll /r:Microsoft.Web.WebView2.WinForms.dll \
//     App.cs
//
// Usage: DSH Desktop.exe [url]   (defaults to http://127.0.0.1:3080)
//
// Features:
// - Single instance (named mutex); a second launch restores the main window
//   and exits with code 42 (the launcher must not stop the service then).
// - The X button of the MAIN window minimizes to the system tray; exit via the
//   tray menu. Detached (child) windows close directly with X.
// - Session detaching: an injected script watches the sidebar session rows.
//   Dragging a session row out of the sidebar (or out of the window entirely)
//   opens a NEW application window at the mouse-release position showing that
//   session; when the dragged session was the current one, the source window
//   switches to the new-session screen. The host tracks the cursor during the
//   drag, so releasing outside the window works without relying on page
//   coordinates.
//
// Test seams (harmless in normal use):
// - env DSH_DESKTOP_AUTOCLOSE=exit: the main window's X closes instead of tray.
// - env DSH_DETACH_DEBUG=1: host appends detach-open events to
//   %TEMP%\dsh-detach-opened.log (used by automated tests).

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace DshDesktop
{
    internal static class Program
    {
        private const string MutexNameBase = @"Local\DSHDesktop.SingleInstance";
        internal const string ShowEventName = @"Local\DSHDesktop.ShowRequest";
        internal const int AlreadyRunningExitCode = 42;
        private static System.Threading.Mutex _mutex;

        // Test seam: DSH_DESKTOP_MUTEX_SUFFIX lets automated tests run a second
        // instance without colliding with the user's running window.
        private static string MutexName
        {
            get
            {
                string suffix = Environment.GetEnvironmentVariable("DSH_DESKTOP_MUTEX_SUFFIX");
                return string.IsNullOrEmpty(suffix) ? MutexNameBase : MutexNameBase + "." + suffix;
            }
        }

        [STAThread]
        private static void Main(string[] args)
        {
            bool createdNew = false;
            try
            {
                _mutex = new System.Threading.Mutex(true, MutexName, out createdNew);
            }
            catch { createdNew = true; }
            if (!createdNew)
            {
                try
                {
                    using (var ev = System.Threading.EventWaitHandle.OpenExisting(ShowEventName))
                    {
                        ev.Set();
                    }
                }
                catch { }
                Environment.Exit(AlreadyRunningExitCode);
                return;
            }

            string url = args.Length > 0 && !string.IsNullOrWhiteSpace(args[0])
                ? args[0]
                : "http://127.0.0.1:3080";
            if (!url.StartsWith("http://") && !url.StartsWith("https://"))
                url = "http://" + url;

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm(url, true));
            System.GC.KeepAlive(_mutex);
        }
    }

    internal sealed class MainForm : Form
    {
        // ---- process-wide state (all windows of this app share it) ----
        private static readonly List<MainForm> OpenWindows = new List<MainForm>();
        private static CoreWebView2Environment _sharedEnv;
        private static string _injectScript;
        private static readonly bool DetachDebug =
            string.Equals(Environment.GetEnvironmentVariable("DSH_DETACH_DEBUG"), "1", StringComparison.Ordinal);

        // ---- one pending sidebar drag per window ----
        private sealed class PendingDrag
        {
            public string Id;
            public string Title;
            public int Group = -1;       // group header ordinal in the source window
            public int Index = -1;       // position of the row inside its group
            public bool Selected;        // the dragged row was the current session
            public double Scale = 1.0;   // DPI scale factor used for coordinate math
            public double RowRightScreenX; // row right edge, screen units
            public double PageX;         // release point reported by the page
            public double PageY;
            public bool DragEndReceived;
            public bool Resolved;
            public int StartedAt;
            public int FallbackDeadline;
        }
        private PendingDrag _pendingDrag;
        private Timer _dragPoll;

        private readonly WebView2 _web;
        private readonly string _url;
        private readonly bool _isPrimary;
        private NotifyIcon _tray;
        private volatile bool _exiting;
        private System.Threading.Thread _showThread;

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern short GetAsyncKeyState(int vKey);
        private const int VK_LBUTTON = 0x01;

        public MainForm(string url, bool isPrimary)
        {
            _url = url;
            _isPrimary = isPrimary;
            Text = "DeepSeek Harness";
            ClientSize = new Size(1440, 900);
            StartPosition = FormStartPosition.CenterScreen;
            MinimumSize = new Size(800, 560);

            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            _web = new WebView2 { Dock = DockStyle.Fill };
            Controls.Add(_web);

            if (_isPrimary)
            {
                BuildTray();
                FormClosing += OnPrimaryFormClosing;
                StartShowListener();
            }
            else
            {
                FormClosing += (s, e) =>
                {
                    if (_exiting) return;
                    // A detached child window closes directly with X.
                };
            }

            Load += OnLoad;
            OpenWindows.Add(this);
            FormClosed += (s, e) => OpenWindows.Remove(this);
        }

        private double UiScale
        {
            get
            {
                try { return (double)DeviceDpi / 96.0; } catch { return 1.0; }
            }
        }

        // ------------------------------------------------------------------
        // Tray (primary window only)
        // ------------------------------------------------------------------
        private void BuildTray()
        {
            _tray = new NotifyIcon();
            try { _tray.Icon = Icon ?? Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
            _tray.Text = "DeepSeek Harness";
            _tray.Visible = false;
            _tray.DoubleClick += (s, e) => RestoreFromTray();

            var menu = new ContextMenuStrip();
            var showItem = new ToolStripMenuItem("显示窗口");
            showItem.Click += (s, e) => RestoreFromTray();
            var exitItem = new ToolStripMenuItem("退出");
            exitItem.Click += (s, e) => ExitApp();
            menu.Items.Add(showItem);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(exitItem);
            _tray.ContextMenuStrip = menu;
        }

        private void MinimizeToTray()
        {
            Hide();
            _tray.Visible = true;
            _tray.ShowBalloonTip(2500, "DeepSeek Harness",
                "已最小化到系统托盘，双击托盘图标恢复窗口。", ToolTipIcon.Info);
        }

        private void RestoreFromTray()
        {
            Show();
            WindowState = FormWindowState.Normal;
            BringToFront();
            Activate();
        }

        private void ExitApp()
        {
            _exiting = true;
            foreach (var w in OpenWindows.ToArray())
            {
                try { w.Close(); } catch { }
            }
        }

        private void OnPrimaryFormClosing(object sender, FormClosingEventArgs e)
        {
            if (_exiting) return;

            string auto = Environment.GetEnvironmentVariable("DSH_DESKTOP_AUTOCLOSE");
            if (auto == "exit") { _exiting = true; return; }

            // The X button of the main window minimizes to the system tray.
            e.Cancel = true;
            MinimizeToTray();
        }

        private void StartShowListener()
        {
            _showThread = new System.Threading.Thread(() =>
            {
                try
                {
                    using (var ev = new System.Threading.EventWaitHandle(
                        false, System.Threading.EventResetMode.AutoReset, Program.ShowEventName))
                    {
                        while (!_exiting)
                        {
                            if (ev.WaitOne(1000))
                            {
                                try { BeginInvoke(new Action(RestoreFromTray)); } catch { }
                            }
                        }
                    }
                }
                catch { }
            });
            _showThread.IsBackground = true;
            _showThread.Name = "DSHShowListener";
            _showThread.Start();
        }

        // ------------------------------------------------------------------
        // WebView2 setup (every window)
        // ------------------------------------------------------------------
        private static string InjectScript()
        {
            if (_injectScript != null) return _injectScript;
            _injectScript = @"(function () {
  var NEW_SESSION_LABELS = ['新建会话', 'New session'];

  function send(msg) {
    try {
      if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
        window.chrome.webview.postMessage(JSON.stringify(msg));
      }
    } catch (e) {}
  }
  function rowOf(e) {
    var t = e.target;
    return t && t.closest ? t.closest('[role=""treeitem""]') : null;
  }
  function rowTitle(row) {
    var best = '';
    var spans = row.querySelectorAll('span');
    for (var i = 0; i < spans.length; i++) {
      var t = (spans[i].textContent || '').trim();
      if (t.length > best.length) best = t;
    }
    return best;
  }
  function hasSpan(row, text) {
    var spans = row.querySelectorAll('span');
    for (var i = 0; i < spans.length; i++) {
      if ((spans[i].textContent || '').trim() === text) return true;
    }
    return false;
  }
  // Group header ordinal + position of the row inside its group. Works for
  // collapsed groups too: slice(0, N) preserves relative order.
  function groupInfo(row) {
    var headers = document.querySelectorAll('[role=""treeitem""][aria-expanded]');
    var group = -1;
    for (var i = 0; i < headers.length; i++) {
      if (headers[i].compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING) group = i;
    }
    if (group < 0) return { group: -1, index: -1 };
    var header = headers[group];
    var index = 0;
    var sib = row.previousElementSibling;
    while (sib && sib !== header) {
      if (sib.hasAttribute && sib.hasAttribute('aria-selected')) index++;
      sib = sib.previousElementSibling;
    }
    return { group: group, index: index };
  }

  // ---- drag a session row out of the sidebar ----
  document.addEventListener('dragstart', function (e) {
    var row = rowOf(e);
    if (!row || row.getAttribute('aria-selected') === null) return;
    var id = null;
    try { id = e.dataTransfer.getData('text/plain'); } catch (err) {}
    var g = groupInfo(row);
    var rect = row.getBoundingClientRect();
    send({
      type: 'dsh-drag-start',
      id: id || '',
      title: rowTitle(row),
      group: g.group,
      index: g.index,
      rightX: rect.right,
      selected: row.getAttribute('aria-selected') === 'true'
    });
  }, true);

  document.addEventListener('dragend', function (e) {
    send({ type: 'dsh-drag-end', x: e.clientX, y: e.clientY });
  }, true);

  // ---- open a detached session in this (new) window ----
  function openDetached() {
    var params = new URLSearchParams(window.location.search);
    var id = params.get('detach') || '';
    var title = params.get('title') || '';
    var group = -1, index = -1;
    try { var gv = parseInt(params.get('group'), 10); if (!isNaN(gv)) group = gv; } catch (e) {}
    try { var iv = parseInt(params.get('index'), 10); if (!isNaN(iv)) index = iv; } catch (e) {}
    if (!id && !title) return;
    try { history.replaceState(null, '', window.location.pathname + window.location.hash); } catch (e) {}

    function findRow() {
      // Expand every collapsed group so all session rows are in the DOM.
      var groups = document.querySelectorAll('[role=""treeitem""][aria-expanded=""false""]');
      for (var i = 0; i < groups.length; i++) {
        try { if (groups[i].getAttribute('aria-expanded') === 'false') groups[i].click(); } catch (e) {}
      }
      var all = document.querySelectorAll('[role=""treeitem""]');
      // 1) exact session id when the web app exposes data-session-id
      if (id) {
        for (var i = 0; i < all.length; i++) {
          if (all[i].getAttribute && all[i].getAttribute('data-session-id') === id) return all[i];
        }
      }
      // 2) same group header + same position inside the group (list order is stable)
      if (group >= 0 && index >= 0) {
        var header = null;
        for (var i = 0; i < all.length; i++) {
          if (all[i].getAttribute && all[i].getAttribute('aria-expanded') !== null) {
            if (--group < 0) { header = all[i]; break; }
          }
        }
        if (header) {
          var seen = -1;
          for (var i = 0; i < all.length; i++) {
            if (all[i] === header) { seen = -1; continue; }
            if (seen < 0) continue;
            if (all[i].getAttribute && all[i].getAttribute('aria-expanded') !== null) break;
            if (!all[i].getAttribute || all[i].getAttribute('aria-selected') === null) continue;
            seen++;
            if (seen === index) {
              if (!title || hasSpan(all[i], title)) return all[i];
            }
          }
        }
      }
      // 3) first row whose title matches
      if (title) {
        for (var i = 0; i < all.length; i++) {
          if (all[i].getAttribute && all[i].getAttribute('aria-selected') !== null && hasSpan(all[i], title)) return all[i];
        }
      }
      return null;
    }

    var tries = 0;
    var timer = setInterval(function () {
      var row = findRow();
      if (row) {
        clearInterval(timer);
        try { row.click(); } catch (e) {}
        send({ type: 'dsh-detach-opened', id: id, title: title });
        return;
      }
      if (++tries > 120) clearInterval(timer);   // give up after ~30 s
    }, 250);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', openDetached);
  } else {
    openDetached();
  }
})();";
            return _injectScript;
        }

        private void OnWebMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            string json = null;
            try { json = e.TryGetWebMessageAsString(); } catch { }
            if (string.IsNullOrWhiteSpace(json)) return;

            if (json.Contains("\"dsh-drag-start\""))
            {
                StartDetachDrag(
                    ExtractField(json, "id") ?? "",
                    ExtractField(json, "title") ?? "",
                    ExtractInt(json, "group", -1),
                    ExtractInt(json, "index", -1),
                    ExtractDouble(json, "rightX", 0),
                    json.Contains("\"selected\":true"));
            }
            else if (json.Contains("\"dsh-drag-end\""))
            {
                EndDetachDrag(ExtractDouble(json, "x", 0), ExtractDouble(json, "y", 0));
            }
            else if (json.Contains("\"dsh-detach-opened\"") && DetachDebug)
            {
                try
                {
                    string id = ExtractField(json, "id") ?? "";
                    string title = ExtractField(json, "title") ?? "";
                    File.AppendAllText(
                        Path.Combine(Path.GetTempPath(), "dsh-detach-opened.log"),
                        DateTime.Now.ToString("HH:mm:ss.fff") + " opened id=" + id + " title=" + title + "\r\n",
                        System.Text.Encoding.UTF8);
                }
                catch { }
            }
        }

        private static string ExtractField(string json, string field)
        {
            var m = Regex.Match(json, "\"" + field + "\":\"((?:[^\"\\\\]|\\\\.)*)\"");
            return m.Success ? m.Groups[1].Value : null;
        }

        private static int ExtractInt(string json, string field, int fallback)
        {
            var m = Regex.Match(json, "\"" + field + "\":(-?\\d+)");
            int v;
            return m.Success && int.TryParse(m.Groups[1].Value, out v) ? v : fallback;
        }

        private static double ExtractDouble(string json, string field, double fallback)
        {
            var m = Regex.Match(json, "\"" + field + "\":(-?\\d+(?:\\.\\d+)?)");
            double v;
            return m.Success && double.TryParse(m.Groups[1].Value, out v) ? v : fallback;
        }

        // ------------------------------------------------------------------
        // Session detach drag handling
        // ------------------------------------------------------------------
        private void StartDetachDrag(string id, string title, int group, int index, double rightX, bool selected)
        {
            CancelDetachDrag();
            double scale = UiScale;
            _pendingDrag = new PendingDrag
            {
                Id = id,
                Title = title,
                Group = group,
                Index = index,
                Selected = selected,
                Scale = scale,
                RowRightScreenX = (Left + rightX) * scale,
                StartedAt = Environment.TickCount
            };
            StartDragPoll();
        }

        private void EndDetachDrag(double x, double y)
        {
            var drag = _pendingDrag;
            if (drag == null) return;
            double scale = drag.Scale;
            drag.PageX = (Left + x) * scale;
            drag.PageY = (Top + y) * scale;
            drag.DragEndReceived = true;
            if (IsInsideWindow(drag.PageX, drag.PageY, scale))
            {
                // In-window release: page coordinates are exact.
                ResolveDrag(drag, drag.PageX, drag.PageY);
            }
            else
            {
                // Release outside the window: wait briefly for the cursor poll
                // to capture the true screen position, then fall back.
                drag.FallbackDeadline = Environment.TickCount + 1500;
            }
        }

        private bool IsInsideWindow(double screenX, double screenY, double scale)
        {
            double left = Left * scale, top = Top * scale;
            double right = (Left + Width) * scale, bottom = (Top + Height) * scale;
            return screenX >= left && screenX <= right && screenY >= top && screenY <= bottom;
        }

        private void StartDragPoll()
        {
            StopDragPoll();
            _dragPoll = new Timer { Interval = 40 };
            _dragPoll.Tick += OnDragPollTick;
            _dragPoll.Start();
        }

        private void StopDragPoll()
        {
            if (_dragPoll != null)
            {
                try { _dragPoll.Stop(); _dragPoll.Dispose(); } catch { }
                _dragPoll = null;
            }
        }

        private void OnDragPollTick(object sender, EventArgs e)
        {
            var drag = _pendingDrag;
            if (drag == null) { StopDragPoll(); return; }
            if (drag.Resolved) { StopDragPoll(); return; }

            bool pressed = (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0;
            if (!pressed)
            {
                // Button released: use the real cursor position (authoritative
                // for releases outside the window).
                ResolveDrag(drag, Cursor.Position.X, Cursor.Position.Y);
                return;
            }
            if (drag.DragEndReceived && Environment.TickCount > drag.FallbackDeadline)
            {
                ResolveDrag(drag, drag.PageX, drag.PageY);
                return;
            }
            if (Environment.TickCount - drag.StartedAt > 300000) CancelDetachDrag();
        }

        private void ResolveDrag(PendingDrag drag, double screenX, double screenY)
        {
            if (drag.Resolved) return;
            drag.Resolved = true;
            if (ReferenceEquals(_pendingDrag, drag)) _pendingDrag = null;
            StopDragPoll();

            double scale = drag.Scale;
            bool outside = !IsInsideWindow(screenX, screenY, scale);
            bool beyondRow = screenX > drag.RowRightScreenX + 24 * scale;
            if (!outside && !beyondRow) return;   // dropped inside the sidebar — leave to the app

            OpenDetachedWindow(drag.Id, drag.Title, drag.Group, drag.Index,
                (int)Math.Round(screenX / scale), (int)Math.Round(screenY / scale));
            if (drag.Selected) ClickNewSession();
        }

        private void CancelDetachDrag()
        {
            _pendingDrag = null;
            StopDragPoll();
        }

        private void ClickNewSession()
        {
            try
            {
                string script = "(function(){var labels=['新建会话','New session'];for(var i=0;i<labels.length;i++){var b=document.querySelector('button[aria-label=\"'+labels[i]+'\"]');if(b){b.click();return true;}}return false;})();";
                _web.CoreWebView2.ExecuteScriptAsync(script);
            }
            catch { }
        }

        private void OpenDetachedWindow(string id, string title, int group, int index, int x, int y)
        {
            string baseUrl = _url;
            int q = baseUrl.IndexOf('?');
            if (q >= 0) baseUrl = baseUrl.Substring(0, q);
            string url = baseUrl + "?detach=" + Uri.EscapeDataString(id ?? "") +
                         "&title=" + Uri.EscapeDataString(title ?? "") +
                         "&group=" + group + "&index=" + index;
            try
            {
                var win = new MainForm(url, false);
                win.StartPosition = FormStartPosition.Manual;
                var wa = Screen.FromPoint(new Point(x, y)).WorkingArea;
                int left = x, top = y;
                if (left + win.Width > wa.Right) left = Math.Max(wa.Left, wa.Right - win.Width);
                if (top + win.Height > wa.Bottom) top = Math.Max(wa.Top, wa.Bottom - win.Height);
                if (left < wa.Left) left = wa.Left;
                if (top < wa.Top) top = wa.Top;
                win.Location = new Point(left, top);
                win.Show();
                win.BringToFront();
                win.Activate();
            }
            catch { }
        }

        // ------------------------------------------------------------------
        // Form lifecycle
        // ------------------------------------------------------------------
        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            _exiting = true;
            CancelDetachDrag();
            try { if (_web != null) _web.Dispose(); } catch { }
            if (_tray != null)
            {
                try { _tray.Visible = false; _tray.Dispose(); } catch { }
                _tray = null;
            }
            base.OnFormClosed(e);
        }

        private async void OnLoad(object sender, EventArgs e)
        {
            try
            {
                string dir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                string userData = Path.Combine(dir ?? ".", "user-data");
                Directory.CreateDirectory(userData);

                if (_sharedEnv == null)
                {
                    _sharedEnv = await CoreWebView2Environment.CreateAsync(null, userData, null);
                }
                await _web.EnsureCoreWebView2Async(_sharedEnv);

                // Inject the session-detach script before the first navigation.
                await _web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(InjectScript());

                _web.CoreWebView2.WebMessageReceived += OnWebMessage;
                _web.CoreWebView2.NewWindowRequested += (s, e2) =>
                {
                    // Keep every navigation inside app windows.
                    e2.Handled = true;
                    try
                    {
                        var win = new MainForm(e2.Uri, false);
                        win.Show();
                    }
                    catch { }
                };

                _web.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
                _web.CoreWebView2.Settings.AreDevToolsEnabled = true;
                _web.CoreWebView2.Settings.IsStatusBarEnabled = false;

                _web.CoreWebView2.DocumentTitleChanged += (s, e2) =>
                {
                    if (!string.IsNullOrWhiteSpace(_web.CoreWebView2.DocumentTitle))
                        Text = _web.CoreWebView2.DocumentTitle;
                };

                _web.CoreWebView2.Navigate(_url);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "无法启动 DeepSeek Harness 桌面窗口：\n\n" + ex.Message,
                    "DeepSeek Harness",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                Application.Exit();
            }
        }
    }
}
