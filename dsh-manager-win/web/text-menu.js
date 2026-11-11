// dsh-manager：给「可编辑控件」（会话输入框、搜索框等）补一个右键菜单：剪切 / 复制 / 粘贴 / 全选。
//
// 背景：为了让右栏预览的右键菜单不弹浏览器的“保存网页”，WebView2 的默认右键菜单被全局关掉了，
// 副作用就是输入框里右键也没了复制/粘贴。这里自己补一个，只在可编辑元素上生效。
(function () {
  if (window.__dshTextMenu) return;
  window.__dshTextMenu = true;

  var MENU_ID = 'dsh-text-menu';

  function closeMenu() {
    var m = document.getElementById(MENU_ID);
    if (m) m.remove();
  }

  function editableOf(el) {
    var node = el;
    for (var i = 0; node && i < 8; i++) {
      var tag = (node.tagName || '').toLowerCase();
      if (tag === 'textarea') return node;
      if (tag === 'input') {
        var type = (node.getAttribute('type') || 'text').toLowerCase();
        if (['text', 'search', 'url', 'tel', 'email', 'password', 'number', ''].indexOf(type) >= 0) return node;
        return null;
      }
      var ce = node.getAttribute && node.getAttribute('contenteditable');
      if (ce === '' || ce === 'true' || ce === 'plaintext-only') return node;
      node = node.parentElement;
    }
    return null;
  }

  function isField(el) {
    var tag = (el.tagName || '').toLowerCase();
    return tag === 'textarea' || tag === 'input';
  }

  function selectedText(el) {
    try {
      if (isField(el)) {
        var a = el.selectionStart, b = el.selectionEnd;
        if (typeof a === 'number' && typeof b === 'number' && b > a) return el.value.slice(a, b);
        return '';
      }
      var sel = window.getSelection();
      return sel ? String(sel) : '';
    } catch (e) { return ''; }
  }

  // 点菜单会把焦点还给输入框，而 focus() 往往会把选区折叠成光标；
  // 所以先把选区存下来，focus 之后再恢复，否则剪切/复制会拿到空选区。
  function captureSelection(el) {
    try {
      if (isField(el)) {
        return { a: el.selectionStart, b: el.selectionEnd };
      }
      var sel = window.getSelection();
      if (sel && sel.rangeCount > 0) return { range: sel.getRangeAt(0).cloneRange() };
    } catch (e) {}
    return null;
  }

  function restoreSelection(el, info) {
    if (!info) return;
    try {
      if (isField(el)) {
        if (typeof info.a === 'number' && typeof info.b === 'number') el.setSelectionRange(info.a, info.b);
        return;
      }
      if (info.range) {
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(info.range);
      }
    } catch (e) {}
  }

  function fireInput(el) {
    try {
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (e) {}
  }

  function replaceSelection(el, text) {
    if (isField(el)) {
      var a = el.selectionStart, b = el.selectionEnd;
      if (typeof a !== 'number' || typeof b !== 'number') { el.value += text; }
      else { el.value = el.value.slice(0, a) + text + el.value.slice(b); el.selectionStart = el.selectionEnd = a + text.length; }
      fireInput(el);
      return true;
    }
    // contenteditable：优先用 execCommand，失败则手工插节点
    try {
      if (document.execCommand('insertText', false, text)) { fireInput(el); return true; }
    } catch (e) {}
    try {
      var sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) { el.appendChild(document.createTextNode(text)); fireInput(el); return true; }
      sel.deleteFromDocument();
      var range = sel.getRangeAt(0);
      var node = document.createTextNode(text);
      range.insertNode(node);
      range.setStartAfter(node); range.collapse(true);
      sel.removeAllRanges(); sel.addRange(range);
      fireInput(el);
      return true;
    } catch (e) { return false; }
  }

  function deleteSelection(el) {
    if (isField(el)) {
      var a = el.selectionStart, b = el.selectionEnd;
      if (typeof a === 'number' && typeof b === 'number' && b > a) {
        el.value = el.value.slice(0, a) + el.value.slice(b);
        el.selectionStart = el.selectionEnd = a;
        fireInput(el);
        return true;
      }
      return false;
    }
    try {
      var sel = window.getSelection();
      if (sel && sel.rangeCount > 0 && String(sel).length > 0) {
        sel.deleteFromDocument();
        fireInput(el);
        return true;
      }
    } catch (e) {}
    return false;
  }

  function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text);
      }
    } catch (e) {}
    try {
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
      document.body.appendChild(ta); ta.select();
      document.execCommand('copy');
      ta.remove();
      return Promise.resolve(true);
    } catch (e) { return Promise.resolve(false); }
  }

  function readClipboard() {
    try {
      if (navigator.clipboard && navigator.clipboard.readText) return navigator.clipboard.readText();
    } catch (e) {}
    return Promise.reject(new Error('no clipboard api'));
  }

  function showMenu(x, y, el) {
    closeMenu();
    var sel = selectedText(el);
    var hasSel = sel.length > 0;

    var items = [
      { id: 'cut', label: '剪切', ok: hasSel },
      { id: 'copy', label: '复制', ok: hasSel },
      { id: 'paste', label: '粘贴', ok: true },
      { id: 'selectall', label: '全选', ok: true },
    ];

    var menu = document.createElement('div');
    menu.id = MENU_ID;
    menu.setAttribute('style', [
      'position:fixed', 'z-index:2147483000', 'min-width:150px',
      'padding:6px', 'border-radius:10px',
      'background:rgba(255,255,255,.98)',
      'border:1px solid rgba(0,0,0,.10)',
      'box-shadow:0 12px 28px rgba(0,0,0,.16)',
      'font:13px/1.4 "Segoe UI","Microsoft YaHei",sans-serif',
      'color:#1b1b1f', 'user-select:none'
    ].join(';'));

    items.forEach(function (it) {
      var row = document.createElement('div');
      row.textContent = it.label;
      row.setAttribute('style', [
        'padding:7px 12px', 'border-radius:7px',
        'cursor:' + (it.ok ? 'pointer' : 'not-allowed'),
        'opacity:' + (it.ok ? '1' : '.45'), 'white-space:nowrap'
      ].join(';'));
      if (it.ok) {
        row.addEventListener('mouseenter', function () { row.style.background = 'rgba(0,0,0,.06)'; });
        row.addEventListener('mouseleave', function () { row.style.background = 'transparent'; });
        row.addEventListener('mousedown', function (ev) { ev.preventDefault(); });  // 保住输入框焦点
        row.addEventListener('click', function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          closeMenu();
          var selInfo = captureSelection(el);
          try { el.focus(); } catch (e) {}
          restoreSelection(el, selInfo);
          if (it.id === 'copy') copyText(selectedText(el));
          else if (it.id === 'cut') {
            var t = selectedText(el);
            var finish = function () { restoreSelection(el, selInfo); deleteSelection(el); };
            copyText(t).then(finish, finish);
          }
          else if (it.id === 'paste') readClipboard().then(function (text) { if (text) replaceSelection(el, text); }, function () { });
          else if (it.id === 'selectall') {
            if (isField(el)) { try { el.select(); } catch (e) {} }
            else { try { var r = document.createRange(); r.selectNodeContents(el); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); } catch (e) {} }
          }
        });
      }
      menu.appendChild(row);
    });

    document.body.appendChild(menu);
    var rect = menu.getBoundingClientRect();
    menu.style.left = Math.max(4, Math.min(x, window.innerWidth - rect.width - 8)) + 'px';
    menu.style.top = Math.max(4, Math.min(y, window.innerHeight - rect.height - 8)) + 'px';
  }

  document.addEventListener('contextmenu', function (e) {
    var el = editableOf(e.target);
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    showMenu(e.clientX, e.clientY, el);
  }, true);

  document.addEventListener('mousedown', function (e) {
    var m = document.getElementById(MENU_ID);
    if (m && !m.contains(e.target)) closeMenu();
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); }, true);
  window.addEventListener('blur', closeMenu);
  window.addEventListener('resize', closeMenu);
})();
