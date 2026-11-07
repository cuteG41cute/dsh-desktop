// dsh-manager：把「文件树里的文件/目录行」和「会话里的交付文件卡」拖出到系统（桌面/资源管理器/输入框）。
// - 文件树行：<li data-files-entry="file|directory" data-files-path="C:\abs\path">
// - 交付卡：<div data-presented-file><button class="_cardPreview" title="C:\abs\path">
// 两者都不是原生 draggable，所以用 mousedown + 位移阈值发起，交给宿主做原生 OLE 拖放。
(function () {
  if (window.__dshDragOut) return;
  window.__dshDragOut = true;

  var press = null;

  function isPath(s) {
    if (!s) return false;
    s = String(s).trim();
    return /^[A-Za-z]:[\\/]/.test(s) || /^\\\\[^\\]/.test(s);
  }

  function pathOf(el) {
    // 1) 右栏文件树的行
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

    // 2) 会话里的交付文件卡（title 上是绝对路径）
    if (el && el.closest) {
      var card = el.closest('[data-presented-file]');
      if (card) {
        var btn = card.querySelector('button[title]');
        var t = btn ? btn.getAttribute('title') : null;
        if (isPath(t)) return String(t).trim();
        var any = card.querySelector('[title]');
        var t2 = any ? any.getAttribute('title') : null;
        if (isPath(t2)) return String(t2).trim();
      }
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
    // 原生 HTML5 拖拽如被触发，一律拦下（由宿主接管）
    if (pathOf(e.target)) { e.preventDefault(); }
  }, true);
})();
