using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows;
using Microsoft.Web.WebView2.Core;

namespace DshManager
{
    /// <summary>
    /// 会话窗口里的「右栏预览增强」：图片/PDF 缩放平移、右键保存/复制/显示、文件拖出保存。
    /// JS 侧脚本沿用旧桌面版（web/preview-tools.js），这里补齐宿主侧处理。
    /// </summary>
    public partial class DshWebWindow
    {
        /// <summary>
        /// 预览/文件增强的注入：**按实例的 dsh 版本分流**。
        ///   0.1.x  → 旧 UI：用旧桌面版那份 preview-tools.js（它当年就是为这套 DOM 写的）
        ///   >=0.2.x → 新 UI：只用我们自己新写的 image-pan / file-dragout（缩放和右键交给官方）
        /// 拿不到版本时按「新 UI」处理，并在 web.log 里留一行标记，方便以后排查。
        /// </summary>
        private void AttachPreviewTools(CoreWebView2 core)
        {
            try
            {
                core.WebMessageReceived += OnPreviewMessage;
                // 顶掉 WebView2 自带的右键菜单（“保存网页/打印/检查”），预览区和交付卡由 preview-menu.js 接管
                try { core.Settings.AreDefaultContextMenusEnabled = false; } catch { }
                // 粘贴要用 navigator.clipboard.readText()，需要放行剪贴板读取权限
                try
                {
                    core.PermissionRequested += (_, e) =>
                    {
                        try
                        {
                            if (e.PermissionKind == CoreWebView2PermissionKind.ClipboardRead) e.State = CoreWebView2PermissionState.Allow;
                        }
                        catch { }
                    };
                }
                catch { }
                var version = _inst.DshVersion ?? "";
                var legacy = IsLegacyUi(version);
                Diag("preview profile: dsh=" + (string.IsNullOrWhiteSpace(version) ? "?" : version)
                     + (legacy ? " -> legacy(0.1.x)" : " -> modern(>=0.2)"));

                if (legacy)
                {
                    // 旧 UI：整包交给旧脚本（缩放/右键/拖出都是它自己那套）
                    var legacyScript = LoadPreviewScript("preview-tools.js");
                    if (!string.IsNullOrEmpty(legacyScript))
                    {
                        _ = core.AddScriptToExecuteOnDocumentCreatedAsync(legacyScript);
                        Diag("preview-tools injected (legacy, " + legacyScript.Length + " chars)");
                    }
                }
                else
                {
                    // 新 UI：只补官方没有的那两半
                    if (Services.AppSettings.WebPan)
                    {
                        var panScript = LoadPreviewScript("image-pan.js");
                        if (!string.IsNullOrEmpty(panScript))
                        {
                            _ = core.AddScriptToExecuteOnDocumentCreatedAsync(panScript);
                            Diag("image-pan injected (" + panScript.Length + " chars)");
                        }
                    }
                    // 可编辑控件（会话输入框/搜索框）的右键菜单：剪切/复制/粘贴/全选
                    var textMenuScript = LoadPreviewScript("text-menu.js");
                    if (!string.IsNullOrEmpty(textMenuScript))
                    {
                        _ = core.AddScriptToExecuteOnDocumentCreatedAsync(textMenuScript);
                        Diag("text-menu injected (" + textMenuScript.Length + " chars)");
                    }
                    // 文件夹拖入：产品靠 __DSH_HOST_PATHS__ 判断“桌面端”，补上这个桥
                    var folderScript = LoadPreviewScript("folder-drop.js");
                    if (!string.IsNullOrEmpty(folderScript))
                    {
                        _ = core.AddScriptToExecuteOnDocumentCreatedAsync(folderScript);
                        Diag("folder-drop injected (" + folderScript.Length + " chars)");
                    }
                    // 预览区/交付卡的右键菜单（保存到桌面、复制路径、资源管理器显示）
                    var menuScript = LoadPreviewScript("preview-menu.js");
                    if (!string.IsNullOrEmpty(menuScript))
                    {
                        _ = core.AddScriptToExecuteOnDocumentCreatedAsync(menuScript);
                        Diag("preview-menu injected (" + menuScript.Length + " chars)");
                    }
                    if (Services.AppSettings.WebDragOut)
                    {
                        // 顶栏插件芯片：窗口窄时收进「插件」抽屉
        // 顶栏芯片抽屉：默认关闭。之前几版会改动页面容器布局，风险大于收益；
        // 想再试时用环境变量 DSH_CHIPS_DRAWER=1 打开。
        var chipsScript = Environment.GetEnvironmentVariable("DSH_CHIPS_DRAWER") == "1"
            ? LoadPreviewScript("chips-drawer.js") : null;
        if (!string.IsNullOrEmpty(chipsScript))
        {
            _ = core.AddScriptToExecuteOnDocumentCreatedAsync(chipsScript);
            Diag("chips-drawer injected (" + chipsScript.Length + " chars)");
            core.NavigationCompleted += async (_, __) =>
            {
                try
                {
                    var alive = await core.ExecuteScriptAsync("String(!!window.__dshChipsDrawer)");
                    Diag("chips-drawer alive=" + alive);
                }
                catch (Exception ex) { Diag("chips-drawer check failed: " + ex.Message); }
            };
        }

        var dragScript = LoadPreviewScript("file-dragout.js");
                        if (!string.IsNullOrEmpty(dragScript))
                        {
                            _ = core.AddScriptToExecuteOnDocumentCreatedAsync(dragScript);
                            Diag("file-dragout injected (" + dragScript.Length + " chars)");
                        }
                    }
                }
            }
            catch (Exception ex) { Diag("preview inject failed: " + ex.Message); }
        }

        /// <summary>0.1.x（含 0.1.5-rc.1）是旧 UI；0.2.x 起换成了现在的 DOM。</summary>
        private static bool IsLegacyUi(string version)
        {
            try
            {
                if (string.IsNullOrWhiteSpace(version)) return false;
                var core = version.Trim();
                var dash = core.IndexOf('-');
                if (dash > 0) core = core.Substring(0, dash);
                var parts = core.Split('.');
                if (parts.Length < 2) return false;
                if (!int.TryParse(parts[0], out var major)) return false;
                if (!int.TryParse(parts[1], out var minor)) return false;
                return major == 0 && minor <= 1;
            }
            catch { return false; }
        }

        /// <summary>导航完成后探测一次 DOM 特征，确认当前版本和注入策略匹配。</summary>
        private async void ProbePreviewDomOnce(CoreWebView2 core)
        {
            try
            {
                await System.Threading.Tasks.Task.Delay(1500);
                var js = @"(function(){
  var files = !!document.querySelector('[data-files-path]');
  var zoomFrame = !!document.querySelector('[data-document-zoom-mode],[class*=_scrollport]');
  var legacyImg = !!document.querySelector('[data-image-preview]');
  window.chrome.webview.postMessage(JSON.stringify({type:'dsh-dom-probe',
     files:files, zoomFrame:zoomFrame, legacyImg:legacyImg}));
})();";
                await core.ExecuteScriptAsync(js);
            }
            catch { }
        }

        private static string LoadPreviewScript(string file = "preview-tools.js")
        {
            try
            {
                var asm = typeof(DshWebWindow).Assembly;
                var name = asm.GetManifestResourceNames()
                    .FirstOrDefault(n => n.EndsWith(file, StringComparison.OrdinalIgnoreCase));
                if (name == null) return null;
                using var s = asm.GetManifestResourceStream(name);
                using var r = new StreamReader(s, Encoding.UTF8);
                return r.ReadToEnd();
            }
            catch { return null; }
        }

        private void OnPreviewMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            string json = null;
            try { json = e.TryGetWebMessageAsString(); } catch { }
            if (string.IsNullOrWhiteSpace(json)) return;

            if (json.Contains("\"dshcd\""))
            {
                Diag("chips-drawer: " + json);
                return;
            }

            if (json.Contains("\"dsh-dom-probe\""))
            {
                Diag("dom probe: " + (json.Length > 400 ? json.Substring(0, 400) : json));
                return;
            }
            if (json.Contains("\"dsh-dom-dump\""))
            {
                Diag("DOMDUMP " + (json.Length > 6000 ? json.Substring(0, 6000) : json));
                return;
            }
            if (json.Contains("\"dsh-drag-out\"")) { StartFileDrag(json); return; }
            if (json.Contains("\"dsh-save-file\"") || json.Contains("\"dsh-save-image\"")
                || json.Contains("\"dsh-copy-image\"") || json.Contains("\"dsh-reveal\""))
            {
                HandleImageMessage(json);
                return;
            }
        }

        // ---------------------------------------------------------------- 拖出到系统

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern short GetAsyncKeyState(int vKey);

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, System.UIntPtr dwExtraInfo);

        private static volatile bool _dragging;

        /// <summary>
        /// 把文件/目录拖出到系统。**这块以前坑过**：如果消息到得晚（用户已经松手），
        /// DoDragDrop 会在“没有按键按下”的状态下进入 OLE 拖动循环，等不到 drop 也等不到 Esc，
        /// 整个 UI 线程就卡死（表现为「管理器未响应」）。所以这里加了三道保险：
        ///   ① 只认 1.2 秒内发出的拖动请求（JS 里带 ts）；
        ///   ② 要求此刻左键仍按下；
        ///   ③ 进入拖动后起一个看门狗，超过 8 秒还没结束就发 Esc 取消。
        /// </summary>
        private void StartFileDrag(string json)
        {
            var src = DecodeB64(Field(json, "pathB64"));
            if (string.IsNullOrEmpty(src)) return;
            if (!File.Exists(src) && !Directory.Exists(src)) return;

            var ts = 0L;
            try { long.TryParse(Field(json, "ts"), out ts); } catch { }
            if (ts > 0)
            {
                var age = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - ts;
                if (age > 1200)
                {
                    Diag("drag out skipped (stale message, " + age + "ms) " + src);
                    return;
                }
            }

            // 左键必须还按着，否则 DoDragDrop 会挂住
            if ((GetAsyncKeyState(0x01) & 0x8000) == 0)
            {
                Diag("drag out skipped (left button already up) " + src);
                Watchdog.Breadcrumb("drag-out skipped (button up)");
                return;
            }

            try
            {
                var data = new DataObject();
                var files = new System.Collections.Specialized.StringCollection { src };
                data.SetFileDropList(files);
                try { data.SetText(src); } catch { }
                try { data.SetData("text/uri-list", new Uri(src).AbsoluteUri); } catch { }
                Diag("drag out start " + src);
                Watchdog.Breadcrumb("drag-out start: " + src);

                _dragging = true;
                var started = DateTime.UtcNow;
                // 看门狗：拖太久就发 Esc 取消（正常情况下拖动几秒内就结束）
                System.Threading.Tasks.Task.Run(async () =>
                {
                    await System.Threading.Tasks.Task.Delay(8000);
                    if (!_dragging) return;
                    Diag("drag out watchdog fired, cancelling");
                    try
                    {
                        keybd_event(0x1B, 0, 0, System.UIntPtr.Zero);
                        await System.Threading.Tasks.Task.Delay(120);
                        keybd_event(0x1B, 0, 2, System.UIntPtr.Zero);
                    }
                    catch { }
                });

                try { DragDrop.DoDragDrop(this, data, DragDropEffects.Copy); }
                finally
                {
                    _dragging = false;
                    Diag("drag out end (" + (int)(DateTime.UtcNow - started).TotalMilliseconds + "ms)");
                    Watchdog.Breadcrumb("drag-out end");
                }
            }
            catch (Exception ex) { Diag("drag out failed: " + ex.Message); }
        }

        // ---------------------------------------------------------------- 保存 / 复制 / 显示

        private void HandleImageMessage(string json)
        {
            var requestId = Field(json, "requestId") ?? "";
            var src = DecodeB64(Field(json, "pathB64"));
            if (json.Contains("\"dsh-reveal\"")) { RevealInExplorer(src); return; }
            if (json.Contains("\"dsh-copy-image\"")) { Reply(json, "dsh-copy-image-result", requestId, CopyImageToClipboard(src)); return; }
            SaveFileFromPage(requestId, DecodeB64(Field(json, "nameB64")), src, Field(json, "data"));
        }

        private void RevealInExplorer(string path)
        {
            try
            {
                if (string.IsNullOrEmpty(path)) return;
                if (File.Exists(path))
                    System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", "/select,\"" + path + "\"") { UseShellExecute = true });
                else if (Directory.Exists(path))
                    System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(path) { UseShellExecute = true });
            }
            catch (Exception ex) { Diag("reveal failed: " + ex.Message); }
        }

        private bool CopyImageToClipboard(string path)
        {
            try
            {
                if (string.IsNullOrEmpty(path) || !File.Exists(path)) return false;
                var img = new System.Windows.Media.Imaging.BitmapImage();
                img.BeginInit();
                img.CacheOption = System.Windows.Media.Imaging.BitmapCacheOption.OnLoad;
                img.UriSource = new Uri(path);
                img.EndInit();
                img.Freeze();
                System.Windows.Clipboard.SetImage(img);
                return true;
            }
            catch (Exception ex) { Diag("copy image failed: " + ex.Message); return false; }
        }

        private void SaveFileFromPage(string requestId, string name, string src, string dataB64)
        {
            try
            {
                var fileName = SafeFileName(name);
                var dlg = new Microsoft.Win32.SaveFileDialog
                {
                    Title = IsImageExt(Path.GetExtension(fileName)) ? "保存图片" : "另存为",
                    InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                    FileName = fileName,
                    Filter = FileFilter(Path.GetExtension(fileName)),
                    AddExtension = true,
                    OverwritePrompt = true,
                };
                Watchdog.Breadcrumb("save dialog opening: " + fileName);
                if (dlg.ShowDialog(this) != true) { Watchdog.Breadcrumb("save dialog cancelled"); ReplyError(requestId, "cancelled"); return; }
                Watchdog.Breadcrumb("save dialog ok: " + dlg.FileName);
                var target = dlg.FileName;
                if (!string.IsNullOrEmpty(src) && File.Exists(src)) File.Copy(src, target, true);
                else if (!string.IsNullOrEmpty(dataB64))
                {
                    var bytes = Convert.FromBase64String(dataB64);
                    File.WriteAllBytes(target, bytes);
                }
                else { ReplyError(requestId, "no-data"); return; }
                Reply(json: null, type: "dsh-save-file-result", requestId: requestId, ok: true, path: target);
                Diag("saved -> " + target);
            }
            catch (Exception ex) { Diag("save failed: " + ex.Message); ReplyError(requestId, "error"); }
        }

        private void ReplyError(string requestId, string reason) =>
            Reply(null, "dsh-save-file-result", requestId, false, null, reason);

        private void Reply(string json, string type, string requestId, bool ok, string path = null, string reason = null)
        {
            try
            {
                var sb = new StringBuilder();
                sb.Append("{\"type\":\"").Append(type).Append("\",\"requestId\":\"").Append(requestId).Append("\",\"ok\":").Append(ok ? "true" : "false");
                if (ok && path != null) sb.Append(",\"pathB64\":\"").Append(B64(path)).Append("\"");
                if (!ok && reason != null) sb.Append(",\"reason\":\"").Append(reason).Append("\"");
                sb.Append('}');
                Web.CoreWebView2?.PostWebMessageAsJson(sb.ToString());
            }
            catch (Exception ex) { Diag("reply failed: " + ex.Message); }
        }

        private static string SafeFileName(string name)
        {
            var n = string.IsNullOrWhiteSpace(name) ? "file" : Path.GetFileName(name.Trim());
            foreach (var c in Path.GetInvalidFileNameChars()) n = n.Replace(c.ToString(), "");
            return string.IsNullOrWhiteSpace(n) ? "file" : n;
        }

        private static bool IsImageExt(string ext)
        {
            if (string.IsNullOrEmpty(ext)) return false;
            const string images = "png;jpg;jpeg;gif;webp;bmp;svg;ico;tif;tiff;avif";
            return (images + ";").IndexOf(ext.TrimStart('.').ToLowerInvariant() + ";") >= 0;
        }

        private static string FileFilter(string ext)
        {
            const string images = "*.png;*.jpg;*.jpeg;*.gif;*.webp;*.bmp;*.svg;*.ico;*.tif;*.tiff;*.avif";
            var e = (ext ?? "").TrimStart('.');
            var own = string.IsNullOrEmpty(e) ? "" : "当前格式 (*." + e + ")|*." + e + "|";
            var img = IsImageExt(ext) ? "图片 (" + images + ")|" + images + "|" : "";
            return own + img + "所有文件 (*.*)|*.*";
        }

        private static string Field(string json, string field)
        {
            try
            {
                var m = Regex.Match(json, "\"" + field + "\":\"((?:[^\"\\\\]|\\\\.)*)\"");
                return m.Success ? m.Groups[1].Value : null;
            }
            catch { return null; }
        }

        private static string DecodeB64(string b64)
        {
            if (string.IsNullOrEmpty(b64)) return null;
            try { return Encoding.UTF8.GetString(Convert.FromBase64String(b64)); } catch { return null; }
        }

        internal static string B64(string s) => Convert.ToBase64String(Encoding.UTF8.GetBytes(s ?? ""));
    }
}
