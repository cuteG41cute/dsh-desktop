// dsh-manager：**仅在右侧预览区**提供右键菜单（保存到桌面 / 复制路径 / 资源管理器显示 / 复制图片）。
//
// 约定：
//   - 只有右键落在「右栏预览」里才接管（documentpreview 模块的 rIfSMq_* 容器 / data-textpreview-path 等）；
//   - 会话正文、输入框、交付卡等地方**一律不接管**（那里右键保持原样）；
//   - 不碰滚轮、不碰缩放。
(function () {
  if (window.__dshMenu) return;
  window.__dshMenu = true;

  var MENU_ID = 'dsh-menu';

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

  // 只认右栏预览容器：documentpreview 包的模块前缀是 rIfSMq_
  function previewRoot(el) {
    var node = el;
    for (var i = 0; node && i < 16; i++) {
      var cls = node.className ? String(node.className) : '';
      if (/(^|\s)rIfSMq_(frame|scrollport|surface)(\s|$)/.test(cls)) return node;
      if (node.hasAttribute && (node.hasAttribute('data-textpreview-path') || node.hasAttribute('data-document-preview'))) return node;
      node = node.parentElement;
    }
    return null;
  }

  // 在预览区里找当前文件的绝对路径
  function pathIn(root) {
    if (!root) return null;
    try {
      var own = root.getAttribute && root.getAttribute('title');
      if (isPath(own)) return own.trim();
    } catch (e) {}
    try {
      var titled = root.querySelectorAll('[title],[data-textpreview-path]');
      for (var i = 0; i < titled.length; i++) {
        var v = titled[i].getAttribute('title') || titled[i].textContent;
        if (isPath(v)) return String(v).trim();
      }
    } catch (e) {}
    try {
      var lines = (root.innerText || '').split(/\r?\n/);
      for (var j = 0; j < lines.length; j++) {
        var line = lines[j].trim();
        if (isPath(line) && line.length < 400) return line;
      }
    } catch (e) {}
    return null;
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
    var items = [
      { id: 'save', label: '保存到桌面…', ok: !!path },
      { id: 'copy-path', label: '复制文件路径', ok: !!path },
      { id: 'reveal', label: '在资源管理器中显示', ok: !!path },
    ];
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
        'padding:7px 10px', 'border-radius:7px',
        'cursor:' + (it.ok ? 'pointer' : 'not-allowed'),
        'opacity:' + (it.ok ? '1' : '.45'), 'white-space:nowrap'
      ].join(';'));
      if (it.ok) {
        row.addEventListener('mouseenter', function () { row.style.background = 'rgba(0,0,0,.06)'; });
        row.addEventListener('mouseleave', function () { row.style.background = 'transparent'; });
        row.addEventListener('click', function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          closeMenu();
          if (it.id === 'save') {
            post({ type: 'dsh-save-file', requestId: String(Date.now()), pathB64: b64(path), nameB64: b64(path.split(/[\\/]/).pop() || 'file') });
          } else if (it.id === 'copy-path') {
            try { navigator.clipboard.writeText(path); } catch (e) {}
          } else if (it.id === 'reveal') {
            post({ type: 'dsh-reveal', pathB64: b64(path) });
          } else if (it.id === 'copy-image') {
            post({ type: 'dsh-copy-image', requestId: String(Date.now()), pathB64: b64(path) });
          }
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
    var root = previewRoot(target);
    if (!root) return;                     // 不在右栏预览里：完全不管，交还给页面/系统

    e.preventDefault();
    e.stopPropagation();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    showMenu(e.clientX, e.clientY, pathIn(root));
  }, true);

  document.addEventListener('mousedown', function (e) {
    var m = document.getElementById(MENU_ID);
    if (m && !m.contains(e.target)) closeMenu();
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); }, true);
  window.addEventListener('blur', closeMenu);
  window.addEventListener('resize', closeMenu);
})();
