// dsh-desktop 注入脚本：右侧栏文件预览增强
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

  function scrollableAncestor(el) {
    var p = el.parentElement, guard = 0;
    while (p && guard++ < 15) {
      var cs = getComputedStyle(p);
      if (/(auto|scroll)/.test(cs.overflowX + cs.overflowY) && p.clientHeight > 80 && p.clientWidth > 160) return p;
      p = p.parentElement;
    }
    return null;
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
    var st = { vp: vp, media: media, frame: media.parentElement || media, zoom: 1, text: !!isText, drag: false, lx: 0, ly: 0 };
    state.set(vp, st);
    vp.classList.add(VP);
    if (media.tagName === 'IMG') media.draggable = false;

    vp.addEventListener('wheel', function (e) {
      if (e.shiftKey) return;                       // Shift+滚轮：交给浏览器做水平滚动
      if (st.text && !(e.ctrlKey || e.metaKey)) return;  // 文本：普通滚轮保持滚动，Ctrl 才缩放
      if (!e.deltaY) return;
      e.preventDefault(); e.stopPropagation();
      var k = st.zoom * Math.exp(-e.deltaY * STEP);
      showBadge(vp, applyZoom(st, k, e.clientX, e.clientY) + '%');
    }, { passive: false, capture: true });

    if (!st.text) {
      vp.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        var t = e.target;
        if (t.closest && t.closest('a,button,input,textarea,select,[contenteditable="true"],[role="button"]')) return;
        if (vp.scrollWidth <= vp.clientWidth + 1 && vp.scrollHeight <= vp.clientHeight + 1 && st.zoom === 1) return;
        st.drag = true; st.lx = e.clientX; st.ly = e.clientY;
        vp.classList.add(PAN);
        e.preventDefault();
      }, true);
      vp.addEventListener('dblclick', function (e) {
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

  window.addEventListener('mousemove', function (e) {
    var list = document.querySelectorAll('.' + VP);
    for (var i = 0; i < list.length; i++) {
      var st = state.get(list[i]);
      if (!st || !st.drag) continue;
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

  function scan() {
    addStyle();
    var media = document.querySelectorAll('img, canvas, video, pre, [data-code-preview]');
    for (var i = 0; i < media.length; i++) {
      var el = media[i], big = false, isText = false;
      if (el.tagName === 'IMG') big = (el.naturalWidth >= 240 || el.naturalHeight >= 240);
      else if (el.tagName === 'CANVAS') big = (el.width >= 300 && el.height >= 200);
      else if (el.tagName === 'PRE' || el.hasAttribute('data-code-preview')) { isText = true; big = true; }
      if (!big) continue;
      var vp = scrollableAncestor(el);
      if (vp) bind(vp, el, isText);
    }
  }

  var timer = 0;
  function start() {
    try { scan(); } catch (e) {}
    if (!timer) timer = setInterval(function () { try { scan(); } catch (e) {} }, 700);
  }
  // 注入发生在 document-start：此时 document.head 可能还不存在，
  // 因此等 DOM 就绪后再开始扫描（并保证定时器一定注册上）。
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
