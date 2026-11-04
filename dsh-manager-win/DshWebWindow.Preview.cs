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
        private void AttachPreviewTools(CoreWebView2 core)
        {
            try
            {
                core.WebMessageReceived += OnPreviewMessage;
                // preview-tools.js 是按**旧版产品 DOM** 写的，其中图片缩放靠改 frame.style.zoom，
                // 在新版里会把「官方缩放」抵消掉；而且它的 wheel 处理会吃掉整页滚动。
                // 默认**不注入**，只在调试时用 DSH_PREVIEW_TOOLS=1 打开。
                if (Environment.GetEnvironmentVariable("DSH_PREVIEW_TOOLS") == "1")
                {
                    var script = LoadPreviewScript("preview-tools.js");
                    if (!string.IsNullOrEmpty(script))
                    {
                        _ = core.AddScriptToExecuteOnDocumentCreatedAsync(script);
                        Diag("preview-tools injected (" + script.Length + " chars)");
                    }
                }
                // 文件行拖出到系统（右侧文件树里的「文件」行）
                var dragScript = Services.AppSettings.WebDragOut ? LoadPreviewScript("file-dragout.js") : null;
                if (!string.IsNullOrEmpty(dragScript))
                {
                    _ = core.AddScriptToExecuteOnDocumentCreatedAsync(dragScript);
                    Diag("file-dragout injected (" + dragScript.Length + " chars)");
                }
                // 拖动平移（只补官方缺的那一半：官方 Ctrl+滚轮能缩放，但没有拖动）
                var panScript = Services.AppSettings.WebPan ? LoadPreviewScript("image-pan.js") : null;
                if (!string.IsNullOrEmpty(panScript))
                {
                    _ = core.AddScriptToExecuteOnDocumentCreatedAsync(panScript);
                    Diag("image-pan injected (" + panScript.Length + " chars)");
                }
                // 自己的图片缩放先**停用**：它用 document 级 wheel 捕获 + preventDefault，
                // 把整个页面的滚动都吃掉了（用户实测：会话正文/左右栏都不能滚）。
                // 等把官方缩放摸清之后再决定要不要重写这一层。
            }
            catch (Exception ex) { Diag("preview inject failed: " + ex.Message); }
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

        private void StartFileDrag(string json)
        {
            var src = DecodeB64(Field(json, "pathB64"));
            if (string.IsNullOrEmpty(src)) return;
            if (!File.Exists(src) && !Directory.Exists(src)) return;
            try
            {
                var data = new DataObject();
                var files = new System.Collections.Specialized.StringCollection { src };
                data.SetFileDropList(files);
                try { data.SetText(src); } catch { }
                try { data.SetData("text/uri-list", new Uri(src).AbsoluteUri); } catch { }
                Diag("drag out " + src);
                DragDrop.DoDragDrop(this, data, DragDropEffects.Copy);
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
                if (dlg.ShowDialog(this) != true) { ReplyError(requestId, "cancelled"); return; }
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
