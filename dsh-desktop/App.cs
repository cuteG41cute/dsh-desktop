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
// - dsh >= 0.1.5 browser authentication: the WebUI answers 401 unless the
//   request carries the signed session cookie. The launcher resolves that
//   cookie (from the token URL dsh prints, or by signing it with the harness
//   home's durable browser-session secret) and passes it in
//   DSH_DESKTOP_AUTH_COOKIE=name=value (optional DSH_DESKTOP_AUTH_COOKIE_MAXAGE
//   in seconds); this app injects it into the shared WebView2 profile before
//   the first navigation, so windows authenticate even when the WebUI service
//   was started outside the launcher. Without it the window simply loads the
//   URL as before.
//
// Test seams (harmless in normal use):
// - env DSH_DESKTOP_AUTOCLOSE=exit: the main window's X closes instead of tray.
// - env DSH_DETACH_DEBUG=1: host appends detach-open events to
//   %TEMP%\dsh-detach-opened.log (used by automated tests).
// - env DSH_DESKTOP_MUTEX_SUFFIX: run a test instance beside the user's window.

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
            // Per-Monitor V2 DPI awareness is declared in app.manifest
            // (win32) and DSH Desktop.exe.config (WinForms); keeps the
            // WebView2 rendering crisp under any display scaling.

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
            else if (json.Contains("\"dsh-preview-bound\"") && DetachDebug)
            {
                try
                {
                    File.AppendAllText(
                        Path.Combine(Path.GetTempPath(), "dsh-detach-opened.log"),
                        DateTime.Now.ToString("HH:mm:ss.fff") + " preview-bound text=" +
                        json.Contains("\"text\":true") + " viewport=" + ExtractInt(json, "w", 0) + "x" + ExtractInt(json, "h", 0) +
                        " content=" + ExtractInt(json, "sw", 0) + "x" + ExtractInt(json, "sh", 0) + "\r\n",
                        System.Text.Encoding.UTF8);
                }
                catch { }
            }            else if (json.Contains("\"dsh-detach-opened\"") && DetachDebug)
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
        // Top-bar loading ring
        // ------------------------------------------------------------------
        // The WebUI shell renders before sessions and plugins arrive, so the
        // window looks ready while nothing is clickable yet. This shows a small
        // progress ring at the top-right (where the header buttons sit) and
        // drives it from observable signals: document ready, boot manifest,
        // WebSocket connected, composer rendered, then it fades out.
        private static string _loadRingScript;
        private static string LoadRingScript()
        {
            if (_loadRingScript != null) return _loadRingScript;
            _loadRingScript = @"
// 顶栏环形加载进度：窗口打开后、应用真正可交互之前显示，加载完成自动淡出。
// 进度由可观测信号驱动：文档就绪 → boot 清单 → WebSocket 建连 → 外壳渲染 → 数据到达。
(function () {
  if (window.__dshLoadRing) return;
  window.__dshLoadRing = true;

  var MIN_MS = 700, MAX_MS = 25000, FADE_MS = 320;
  var t0 = Date.now(), wsTried = 0, wsOpen = 0, done = false;

  // 在 document-start 抢先包住 WebSocket，用来判断""数据通道是否已连上""
  try {
    var OrigWS = window.WebSocket;
    if (OrigWS && !OrigWS.__dshWrapped) {
      var Wrapped = function (url, protocols) {
        wsTried++;
        var sock = protocols === undefined ? new OrigWS(url) : new OrigWS(url, protocols);
        try { sock.addEventListener('open', function () { wsOpen++; }); } catch (e) {}
        return sock;
      };
      Wrapped.prototype = OrigWS.prototype;
      Wrapped.__dshWrapped = true;
      ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach(function (k) { try { Wrapped[k] = OrigWS[k]; } catch (e) {} });
      window.WebSocket = Wrapped;
    }
  } catch (e) {}

  var STYLE_ID = 'dsh-ring-style', BOX_ID = 'dsh-ring', R = 9, C = 2 * Math.PI * R;

  function build() {
    if (!document.head || document.getElementById(BOX_ID)) return;
    var st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent =
      '#' + BOX_ID + '{position:fixed;top:9px;right:11px;width:26px;height:26px;z-index:2147483000;' +
      'pointer-events:none;opacity:1;transition:opacity ' + FADE_MS + 'ms linear;display:block}' +
      '#' + BOX_ID + ' svg{display:block;transform:rotate(-90deg)}' +
      '#' + BOX_ID + ' .dsh-ring-track{stroke:rgba(120,140,165,.28)}' +
      '#' + BOX_ID + ' .dsh-ring-arc{stroke:#3b5bfd;stroke-linecap:round;transition:stroke-dashoffset 180ms linear}' +
      '#' + BOX_ID + '.dsh-ring-out{opacity:0}';
    document.head.appendChild(st);

    var box = document.createElement('div');
    box.id = BOX_ID;
    box.setAttribute('aria-hidden', 'true');
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', '26'); svg.setAttribute('height', '26');
    svg.setAttribute('viewBox', '0 0 24 24');
    var cx = 12, cy = 12;
    var track = document.createElementNS(NS, 'circle');
    track.setAttribute('class', 'dsh-ring-track');
    track.setAttribute('cx', cx); track.setAttribute('cy', cy); track.setAttribute('r', R);
    track.setAttribute('fill', 'none'); track.setAttribute('stroke-width', '2.4');
    var arc = document.createElementNS(NS, 'circle');
    arc.setAttribute('class', 'dsh-ring-arc');
    arc.setAttribute('cx', cx); arc.setAttribute('cy', cy); arc.setAttribute('r', R);
    arc.setAttribute('fill', 'none'); arc.setAttribute('stroke-width', '2.4');
    arc.setAttribute('stroke-dasharray', C.toFixed(2));
    arc.setAttribute('stroke-dashoffset', C.toFixed(2));
    svg.appendChild(track); svg.appendChild(arc); box.appendChild(svg);
    document.body.appendChild(box);
    return { box: box, arc: arc };
  }

  var ui = null, shown = 0;

  function target() {
    var p = 6;
    var rs = document.readyState;
    if (rs === 'interactive' || rs === 'complete') p = 16;
    if (rs === 'complete') p = 24;
    if (window.__DSH_BOOT__) p = 34;
    if (wsTried) p = 46;
    if (wsOpen) p = 60;
    var shell = document.querySelector('textarea, [contenteditable=""true""], [class*=""composer""], [class*=""Composer""]');
    if (shell) p = 76;
    var rows = document.querySelectorAll('[role=""treeitem""], [class*=""sessionRow""], [class*=""SessionRow""]');
    if (rows.length > 0) p = 92;
    return { p: p, ready: (wsOpen > 0 && !!shell && (Date.now() - t0) > MIN_MS) || (Date.now() - t0) > MAX_MS };
  }

  function tick() {
    if (done) return;
    if (!ui) ui = build();
    var t = target();
    var goal = t.ready ? 100 : t.p;
    shown = Math.max(shown, Math.min(goal, shown + 6));   // 只前进、平滑逼近
    if (ui) ui.arc.setAttribute('stroke-dashoffset', (C * (1 - shown / 100)).toFixed(2));
    if (shown >= 100) {
      done = true;
      if (ui) {
        ui.box.classList.add('dsh-ring-out');
        setTimeout(function () { try { ui.box.remove(); var s = document.getElementById(STYLE_ID); if (s) s.remove(); } catch (e) {} }, FADE_MS + 60);
      }
      return;
    }
    setTimeout(tick, 130);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(tick, 60); });
  } else {
    setTimeout(tick, 60);
  }
})();
";
            return _loadRingScript;
        }

        // ------------------------------------------------------------------
        // Right-sidebar file preview: wheel zoom, drag pan, thicker scrollbars
        // ------------------------------------------------------------------
        // The product renders a document preview inside a scrolling body and
        // shows images/PDF pages at their intrinsic size, so a large file only
        // ever shows a corner in the narrow sidebar. This script upgrades that
        // viewport: wheel = zoom anchored at the cursor (Ctrl+wheel for text
        // and code, whose plain wheel keeps scrolling so text stays readable
        // and selectable), left-drag = pan for images and PDF pages, and the
        // right/bottom scrollbars are thickened from the product's 8px to a
        // grabbable 14px. Double-click toggles fit and 1:1; a one-time hint
        // badge names the gestures on first use.
        // Injected at document start, so it waits for the DOM before touching
        // document.head and never gives up retrying.
        private static string _previewScript;
        private static string PreviewToolsScript()
        {
            if (_previewScript != null) return _previewScript;
            _previewScript = @"
// dsh-desktop 注入脚本：右侧栏文件预览增强
//   · 作用范围**仅限右侧栏的文档/图片预览视口**（[data-sidebar-right-panel] 内的
//     [data-textpreview-body]）；右侧栏收起或预览关闭时全部解绑，原生行为立即恢复
//   · 图片 / PDF：滚轮 = 缩放（以光标为锚点）、左键拖动 = 平移
//   · 文本 / 代码：滚轮仍是原生滚动（保留选中文字），Ctrl+滚轮 = 缩放
//   · 预览区右侧与底部使用加粗的可拖动滑动条（14px，覆盖产品的 8px 细条）
//   · 双击图片/PDF = 适宽 ↔ 1:1 切换；缩放时右上角短暂显示百分比
(function () {
  if (window.__dshPreviewTools) return;
  window.__dshPreviewTools = true;

  var MIN = 0.15, MAX = 8, STEP = 0.0015, PAD = 8;
  var VP = 'dsh-pv-vp', PAN = 'dsh-pv-pan', BADGE = 'dsh-pv-badge', STYLE = 'dsh-pv-style';
  var state = new WeakMap();

  function post(msg) {
    try {
      if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
        window.chrome.webview.postMessage(JSON.stringify(msg));
      }
    } catch (e) {}
  }

  function addStyle() {
    if (!document.head) return;
    if (document.getElementById(STYLE)) return;
    var st = document.createElement('style');
    st.id = STYLE;
    st.textContent =
      '.' + VP + '{overflow:auto !important}' +
      '.' + VP + '::-webkit-scrollbar{width:14px;height:14px}' +
      '.' + VP + '::-webkit-scrollbar-track{background:rgba(128,128,128,.10);border-radius:7px}' +
      '.' + VP + '::-webkit-scrollbar-thumb{background:var(--dsh-scrollbar-thumb,rgba(128,128,128,.55));border-radius:7px;border:3px solid transparent;background-clip:content-box}' +
      '.' + VP + '::-webkit-scrollbar-thumb:hover{background:var(--dsh-scrollbar-thumb-hover,rgba(128,128,128,.85));background-clip:content-box}' +
      '.' + VP + '.' + PAN + '{cursor:grabbing}' +
      '.' + VP + '.' + PAN + ' *{cursor:grabbing !important;user-select:none !important}' +
      '#' + BADGE + '{position:fixed;z-index:2147483000;padding:3px 8px;border-radius:6px;' +
      'font:12px/1.6 var(--dsh-font-family,sans-serif);background:rgba(20,20,20,.82);color:#fff;' +
      'pointer-events:none;opacity:0;transition:opacity .18s}' +
      '#' + BADGE + '.show{opacity:1}';
    document.head.appendChild(st);
  }

  var badgeTimer = 0;
  function showBadge(vp, text, ms) {
    var el = document.getElementById(BADGE);
    if (!el) { el = document.createElement('div'); el.id = BADGE; document.body.appendChild(el); }
    var r = vp.getBoundingClientRect();
    el.textContent = text;
    el.style.left = Math.round(Math.max(8, r.right - 96)) + 'px';
    el.style.top = Math.round(r.top + 10) + 'px';
    el.className = 'show';
    clearTimeout(badgeTimer);
    badgeTimer = setTimeout(function () { el.className = ''; }, ms || 1100);
  }

  // ───────────────────────── 作用范围判定 ─────────────────────────
  // dsh 的右侧栏面板始终留在 DOM 中：展开时 data-sidebar-right-open=""push""，
  // 收起时该属性被移除、面板变成 aria-hidden + visibility:hidden，并被整体移到
  // 窗口右侧之外（grid 列为 0px）。所以「是否生效」以几何可见性为准（跨版本稳定），
  // 属性只作为辅助信号；判定失败就解绑，绝不会作用到对话区或其它滚动容器上。
  function livePanel(vp) {
    if (!vp || !vp.closest) return null;
    var panel = vp.closest('[data-sidebar-right-panel]');
    if (!panel || !panel.isConnected) return null;
    if (panel.getAttribute('aria-hidden') === 'true') return null;
    if (panel.getAttribute('data-sidebar-right-open') === 'false') return null;
    var cs = getComputedStyle(panel);
    if (cs.display === 'none' || cs.visibility === 'hidden') return null;
    var r = panel.getBoundingClientRect();
    if (r.width < 60 || r.right <= 0 || r.left >= window.innerWidth) return null;
    return panel;
  }

  function liveViewport(vp) {
    if (!vp || !vp.isConnected || !vp.closest) return null;
    if (!vp.closest('[data-document-preview]')) return null;   // 只认预览渲染器子树
    if (!livePanel(vp)) return null;
    var r = vp.getBoundingClientRect();
    if (r.width < 40 || r.height < 40) return null;
    return vp;
  }

  function liveState(st) {
    return !!st && st.vp.classList.contains(VP) && liveViewport(st.vp) === st.vp;
  }

  // ───────────────────────── 绑定 / 解绑 ─────────────────────────
  function unbind(vp) {
    var st = state.get(vp);
    if (st) {
      for (var i = 0; i < st.on.length; i++) {
        try { vp.removeEventListener(st.on[i][0], st.on[i][1], st.on[i][2]); } catch (e) {}
      }
      try { if (st.frame && st.frame.style) st.frame.style.zoom = ''; } catch (e) {}
      state.delete(vp);
    }
    vp.classList.remove(VP, PAN);
    var badge = document.getElementById(BADGE);
    if (badge) badge.className = '';
    post({ type: 'dsh-preview-unbound' });
  }

  function on(vp, st, type, fn, capture) {
    var h = function (e) { if (!liveState(st)) return; fn(e); };
    vp.addEventListener(type, h, capture);
    st.on.push([type, h, capture]);
  }

  function box(st) {
    var el = st.frame;
    var w = st.media.naturalWidth || el.scrollWidth || el.getBoundingClientRect().width;
    var h = st.media.naturalHeight || el.scrollHeight || el.getBoundingClientRect().height;
    return { w: w, h: h };
  }

  function fitScale(st) {
    var b = box(st), vp = st.vp;
    var k = Math.min((vp.clientWidth - PAD * 2) / b.w, (vp.clientHeight - PAD * 2) / b.h);
    return Math.max(MIN, Math.min(MAX, k));
  }

  function applyZoom(st, k, cx, cy) {
    var vp = st.vp, r = vp.getBoundingClientRect();
    k = Math.max(MIN, Math.min(MAX, k));
    var ox = (typeof cx === 'number' ? cx - r.left : r.width / 2);
    var oy = (typeof cy === 'number' ? cy - r.top : r.height / 2);
    var px = vp.scrollLeft + ox, py = vp.scrollTop + oy;
    var ratio = k / st.zoom;
    st.frame.style.zoom = (Math.abs(k - 1) < 0.001) ? '' : String(k);
    st.zoom = k;
    vp.scrollLeft = px * ratio - ox;
    vp.scrollTop = py * ratio - oy;
    return Math.round(k * 100);
  }

  function bind(vp, media, isText) {
    if (state.has(vp)) return false;
    var st = { vp: vp, media: media, frame: media.parentElement || media, zoom: 1, text: !!isText,
               drag: false, lx: 0, ly: 0, on: [] };
    state.set(vp, st);
    vp.classList.add(VP);
    if (media.tagName === 'IMG') media.draggable = false;

    on(vp, st, 'wheel', function (e) {
      if (e.shiftKey) return;                       // Shift+滚轮：交给浏览器做水平滚动
      if (st.text && !(e.ctrlKey || e.metaKey)) return;  // 文本：普通滚轮保持滚动，Ctrl 才缩放
      if (!e.deltaY) return;
      e.preventDefault(); e.stopPropagation();
      var k = st.zoom * Math.exp(-e.deltaY * STEP);
      showBadge(vp, applyZoom(st, k, e.clientX, e.clientY) + '%');
    }, { passive: false, capture: true });

    if (!st.text) {
      on(vp, st, 'mousedown', function (e) {
        if (e.button !== 0) return;
        var t = e.target;
        if (t.closest && t.closest('a,button,input,textarea,select,[contenteditable=""true""],[role=""button""]')) return;
        if (vp.scrollWidth <= vp.clientWidth + 1 && vp.scrollHeight <= vp.clientHeight + 1 && st.zoom === 1) return;
        st.drag = true; st.lx = e.clientX; st.ly = e.clientY;
        vp.classList.add(PAN);
        e.preventDefault();
      }, true);
      on(vp, st, 'dblclick', function (e) {
        var fit = fitScale(st);
        var target = Math.abs(st.zoom - fit) < 0.02 ? 1 : fit;
        showBadge(vp, (target === 1 ? '1:1 · ' : '适宽 · ') + applyZoom(st, target, e.clientX, e.clientY) + '%');
      }, true);
    }
    if (!window.__dshPreviewHint) {
      window.__dshPreviewHint = true;
      showBadge(vp, st.text ? 'Ctrl+滚轮缩放' : '滚轮缩放 · 拖动平移 · 双击适宽', 2800);
    }
    post({ type: 'dsh-preview-bound', text: st.text, w: vp.clientWidth, h: vp.clientHeight, sw: vp.scrollWidth, sh: vp.scrollHeight });
    return true;
  }

  // 同一个预览视口里换了文件（切换标签/点开另一个文件）时，媒体元素会变，
  // 需要重新取 frame 并清掉上一份的缩放，否则缩放会作用在已废弃的节点上。
  function refresh(vp, media, isText) {
    var st = state.get(vp);
    if (!st || st.media === media) { if (st) st.text = !!isText; return false; }
    try { if (st.frame && st.frame.style) st.frame.style.zoom = ''; } catch (e) {}
    st.media = media;
    st.frame = media.parentElement || media;
    st.zoom = 1;
    st.text = !!isText;
    st.drag = false;
    vp.classList.remove(PAN);
    if (media.tagName === 'IMG') media.draggable = false;
    return true;
  }

  window.addEventListener('mousemove', function (e) {
    var list = document.querySelectorAll('.' + VP);
    for (var i = 0; i < list.length; i++) {
      var st = state.get(list[i]);
      if (!st || !st.drag || !liveState(st)) continue;
      list[i].scrollLeft -= e.clientX - st.lx;
      list[i].scrollTop -= e.clientY - st.ly;
      st.lx = e.clientX; st.ly = e.clientY;
      e.preventDefault();
    }
  }, true);

  window.addEventListener('mouseup', function () {
    var list = document.querySelectorAll('.' + VP);
    for (var i = 0; i < list.length; i++) {
      var st = state.get(list[i]);
      if (st && st.drag) { st.drag = false; list[i].classList.remove(PAN); }
    }
  }, true);

  // 只认右栏预览里的视口，绝不碰对话区/左栏等其它滚动容器
  function findViewport() {
    var bodies = document.querySelectorAll('[data-textpreview-body]');
    for (var i = 0; i < bodies.length; i++) {
      var vp = bodies[i];
      if (liveViewport(vp) !== vp) continue;
      var media = vp.querySelector('[data-image-preview] img, img, canvas, video');
      if (media && media.tagName === 'IMG' && media.naturalWidth < 240 && media.naturalHeight < 240) media = null;
      if (media && media.tagName === 'CANVAS' && (media.width < 300 || media.height < 200)) media = null;
      if (!media) media = vp.querySelector('[data-textpreview-page], pre, [data-code-preview]');
      return { vp: vp, media: media, text: !media || media.tagName !== 'IMG' };
    }
    return null;
  }

  function scan() {
    addStyle();
    var found = findViewport();
    var target = (found && found.media) ? found.vp : null;
    var list = document.querySelectorAll('.' + VP);
    for (var i = 0; i < list.length; i++) {
      // 右栏收起 / 预览关闭 / 换了视口 → 立即解绑（滑动条与滚轮缩放随之失效）
      if (list[i] !== target || liveViewport(list[i]) !== list[i]) unbind(list[i]);
    }
    if (target && !bind(target, found.media, found.text)) refresh(target, found.media, found.text);
  }

  var timer = 0;
  function start() {
    try { scan(); } catch (e) {}
    if (!timer) timer = setInterval(function () { try { scan(); } catch (e) {} }, 500);
  }
  // 注入发生在 document-start：此时 document.head 可能还不存在，
  // 因此等 DOM 就绪后再开始扫描（并保证定时器一定注册上）。
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
";
            return _previewScript;
        }
        // ------------------------------------------------------------------
        // dsh >= 0.1.5 Web authentication
        // ------------------------------------------------------------------
        // The WebUI answers 401 to an unauthenticated root request; only a URL
        // carrying the process launch token mints the persistent signed session
        // cookie. The launcher resolves that cookie for this origin and hands it
        // over in the environment, which authenticates windows whose service was
        // started elsewhere (no token URL left in any log).
        private static async System.Threading.Tasks.Task ApplyLauncherAuthCookieAsync(CoreWebView2 core, string url)
        {
            string raw = Environment.GetEnvironmentVariable("DSH_DESKTOP_AUTH_COOKIE");
            if (string.IsNullOrEmpty(raw)) return;
            int at = raw.IndexOf('=');
            if (at <= 0) return;
            string name = raw.Substring(0, at).Trim();
            string value = raw.Substring(at + 1).Trim();
            if (name.Length == 0 || value.Length == 0) return;

            string host;
            try { host = new Uri(url).Host; } catch { return; }

            double maxAgeDays = 30.0;
            try
            {
                string rawMaxAge = Environment.GetEnvironmentVariable("DSH_DESKTOP_AUTH_COOKIE_MAXAGE");
                double seconds;
                if (!string.IsNullOrEmpty(rawMaxAge) &&
                    double.TryParse(rawMaxAge, System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out seconds) &&
                    seconds > 0)
                {
                    maxAgeDays = seconds / 86400.0;
                }
            }
            catch { }

            bool applied = false;
            try
            {
                CoreWebView2Cookie cookie = core.CookieManager.CreateCookie(name, value, host, "/");
                cookie.IsHttpOnly = true;
                // A concrete expiry keeps the cookie persistent (not session-only).
                cookie.Expires = DateTime.Now.AddDays(maxAgeDays);
                core.CookieManager.AddOrUpdateCookie(cookie);

                // Read back: proves this profile really holds the cookie.
                var stored = await core.CookieManager.GetCookiesAsync(url);
                foreach (CoreWebView2Cookie c in stored)
                {
                    if (c.Name == name) { applied = true; break; }
                }
            }
            catch { }

            if (DetachDebug)
            {
                try
                {
                    File.AppendAllText(
                        Path.Combine(Path.GetTempPath(), "dsh-detach-opened.log"),
                        DateTime.Now.ToString("HH:mm:ss.fff") + " auth-cookie name=" + name +
                        " host=" + host + " maxAgeDays=" + maxAgeDays.ToString("0.##") +
                        " applied=" + applied + "\r\n",
                        System.Text.Encoding.UTF8);
                }
                catch { }
            }
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

                // Authenticate this window before the first navigation (dsh >= 0.1.5).
                await ApplyLauncherAuthCookieAsync(_web.CoreWebView2, _url);

                // Inject the session-detach script before the first navigation.
                await _web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(InjectScript());
                await _web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(PreviewToolsScript());
                await _web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(LoadRingScript());

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
