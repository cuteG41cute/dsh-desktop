// dsh-manager：预览区 / 交付卡的右键菜单（顶掉浏览器默认的“保存网页”菜单）。
// 只做三件事：保存到桌面（另存为）、复制文件路径、在资源管理器中显示；图片额外给“复制图片”。
// 不碰滚轮、不碰缩放，尽量不打扰产品自己的交互。
(function () {
  if (window.__dshMenu) return;
  window.__dshMenu = true;

  var MENU_ID = 'dsh-menu';
  var lastPath = null;

  function isPath(s) {
    if (!s) return false;
    s = String(s).trim();
    return /^[A-Za-z]:[\\/]/.test(s) || /^\\\\[^\\]/.test(s);
  }

  function b64(s) {
    try { return btoa(unescape(encodeURIComponent(s))); } catch (e) { return ''; }
  }

  function post(msg) {
    try {
      if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
        window.chrome.webview.postMessage(JSON.stringify(msg));
      }
    } catch (e) {}
  }

  // 从元素往上看，找“预览容器”里出现的绝对路径
  function pathNear(el) {
    var node = el;
    for (var depth = 0; node && depth < 10; depth++) {
      // 1) 元素自己的 title
      var t = node.getAttribute && node.getAttribute('title');
      if (isPath(t)) return t.trim();

      // 2) 子孙里的 title
      try {
        var titled = node.querySelectorAll ? node.querySelectorAll('[title],[data-textpreview-path]') : [];
        for (var i = 0; i < titled.length; i++) {
          var v = titled[i].getAttribute('title') || titled[i].textContent;
          if (isPath(v)) return String(v).trim();
        }
      } catch (e) {}

      // 3) 文本里像路径的一行
      try {
        var text = node.innerText || '';
        var lines = text.split(/\r?\n/);
        for (var j = 0; j < lines.length; j++) {
          var line = lines[j].trim();
          if (isPath(line) && line.length < 400) return line;
        }
      } catch (e) {}

      node = node.parentElement;
    }
    return null;
  }

  // 交付卡：<div data-presented-file><button class="..._cardPreview" title="绝对路径">
  function cardPath(el) {
    var card = el.closest ? el.closest('[data-presented-file]') : null;
    if (!card) return null;
    var btn = card.querySelector('button[title]');
    if (btn && isPath(btn.getAttribute('title'))) return btn.getAttribute('title').trim();
    var any = card.querySelector('[title]');
    if (any && isPath(any.getAttribute('title'))) return any.getAttribute('title').trim();
    return null;
  }

  function inPreview(el) {
    var node = el;
    for (var i = 0; node && i < 12; i++) {
      var c = node.className ? String(node.className) : '';
      if (c.indexOf('_surface') >= 0 || c.indexOf('_scrollport') >= 0 || c.indexOf('_frame') >= 0) return true;
      if (node.hasAttribute && (node.hasAttribute('data-document-preview') || node.hasAttribute('data-presented-file'))) return true;
      node = node.parentElement;
    }
    return false;
  }

  function isImagePath(p) {
    return !!p && /\.(png|jpe?g|gif|webp|bmp|svg|ico|tiff?|avif)$/i.test(p);
  }

  function closeMenu() {
    var m = document.getElementById(MENU_ID);
    if (m) m.remove();
  }

  function showMenu(x, y, path) {
    closeMenu();
    var items = [];
    items.push({ id: 'save', label: '保存到桌面…', ok: !!path });
    items.push({ id: 'copy-path', label: '复制文件路径', ok: !!path });
    items.push({ id: 'reveal', label: '在资源管理器中显示', ok: !!path });
    if (isImagePath(path)) items.push({ id: 'copy-image', label: '复制图片', ok: true });

    var menu = document.createElement('div');
    menu.id = MENU_ID;
    menu.setAttribute('style', [
      'position:fixed', 'z-index:2147483000', 'min-width:190px',
      'padding:6px', 'border-radius:10px',
      'background:rgba(255,255,255,.98)',
      'border:1px solid rgba(0,0,0,.10)',
      'box-shadow:0 12px 28px rgba(0,0,0,.16)',
      'font:13px/1.4 "Segoe UI","Microsoft YaHei",sans-serif',
      'color:#1b1b1f', 'user-select:none'
    ].join(';'));

    var head = document.createElement('div');
    head.textContent = path ? (path.split(/[\\/]/).pop() || path) : '未定位到文件路径';
    head.setAttribute('style', 'padding:4px 10px 6px;font-size:12px;color:#8a8a92;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px');
    menu.appendChild(head);

    items.forEach(function (it) {
      var row = document.createElement('div');
      row.textContent = it.label;
      row.setAttribute('style', [
        'padding:7px 10px', 'border-radius:7px', 'cursor:' + (it.ok ? 'pointer' : 'not-allowed'),
        'opacity:' + (it.ok ? '1' : '.45'), 'white-space:nowrap'
      ].join(';'));
      if (it.ok) {
        row.addEventListener('mouseenter', function () { row.style.background = 'rgba(0,0,0,.06)'; });
        row.addEventListener('mouseleave', function () { row.style.background = 'transparent'; });
        row.addEventListener('click', function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          closeMenu();
          if (it.id === 'save') post({ type: 'dsh-save-file', requestId: String(Date.now()), pathB64: b64(path), nameB64: b64(path.split(/[\\/]/).pop() || 'file') });
          else if (it.id === 'copy-path') { try { navigator.clipboard.writeText(path); } catch (e) {} }
          else if (it.id === 'reveal') post({ type: 'dsh-reveal', pathB64: b64(path) });
          else if (it.id === 'copy-image') post({ type: 'dsh-copy-image', requestId: String(Date.now()), pathB64: b64(path) });
        });
      }
      menu.appendChild(row);
    });

    document.body.appendChild(menu);
    var rect = menu.getBoundingClientRect();
    var left = Math.min(x, window.innerWidth - rect.width - 8);
    var top = Math.min(y, window.innerHeight - rect.height - 8);
    menu.style.left = Math.max(4, left) + 'px';
    menu.style.top = Math.max(4, top) + 'px';
  }

  document.addEventListener('contextmenu', function (e) {
    var target = e.target;
    if (!target) return;
    var card = cardPath(target);
    var preview = inPreview(target);
    if (!card && !preview) return;         // 其它区域的右键交还给产品/系统

    var path = card || pathNear(target);
    lastPath = path;
    e.preventDefault();
    e.stopPropagation();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    showMenu(e.clientX, e.clientY, path);
  }, true);

  document.addEventListener('mousedown', function (e) {
    var m = document.getElementById(MENU_ID);
    if (m && !m.contains(e.target)) closeMenu();
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); }, true);
  window.addEventListener('blur', closeMenu);
  window.addEventListener('resize', closeMenu);
})();
