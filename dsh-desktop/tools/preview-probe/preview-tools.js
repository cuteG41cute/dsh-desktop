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
  // dsh 的右侧栏面板始终留在 DOM 中：展开时 data-sidebar-right-open="push"，
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
        if (t.closest && t.closest('a,button,input,textarea,select,[contenteditable="true"],[role="button"]')) return;
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
