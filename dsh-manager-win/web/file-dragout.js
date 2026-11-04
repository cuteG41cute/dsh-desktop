// dsh-manager：把右栏文件树里的「文件行」拖出到系统（桌面/资源管理器/聊天窗口）。
// 新 UI 的行结构：<li data-files-entry="file" data-files-path="/abs/path"><button class="_row">…
// 行本身不是 draggable，所以这里用 mousedown + 位移阈值来发起，交给宿主做原生 OLE 拖放。
(function () {
  if (window.__dshDragOut) return;
  window.__dshDragOut = true;

  var press = null;

  function pathOf(el) {
    var n = el;
    for (var i = 0; n && i < 8; i++) {
      if (n.getAttribute) {
        var kind = n.getAttribute('data-files-entry');
        var p = n.getAttribute('data-files-path');
        // 文件和目录都支持：目录拖出去就是整个文件夹（宿主那边 FileDropList 支持目录）
        if ((kind === 'file' || kind === 'directory') && p) return p;
      }
      n = n.parentElement;
    }
    return null;
  }

  function b64(s) { return btoa(unescape(encodeURIComponent(s))); }

  document.addEventListener('mousedown', function (e) {
    if (e.button !== 0) return;
    var p = pathOf(e.target);
    if (!p) return;
    press = { x: e.clientX, y: e.clientY, path: p, sent: false };
  }, true);

  document.addEventListener('mousemove', function (e) {
    if (!press || press.sent) return;
    if (Math.abs(e.clientX - press.x) < 6 && Math.abs(e.clientY - press.y) < 6) return;
    press.sent = true;
    var path = press.path;
    press = null;
    try { e.preventDefault(); e.stopPropagation(); } catch (err) {}
    try {
      window.chrome.webview.postMessage(JSON.stringify({ type: 'dsh-drag-out', pathB64: b64(path) }));
    } catch (err) {}
  }, true);

  document.addEventListener('mouseup', function () { press = null; }, true);
  document.addEventListener('dragstart', function (e) {
    // 行的原生 HTML5 拖拽如被触发，一律拦下（由宿主接管）
    if (pathOf(e.target)) { e.preventDefault(); }
  }, true);
})();
