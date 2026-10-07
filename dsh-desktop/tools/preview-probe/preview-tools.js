// dsh-desktop 注入脚本：右侧栏「图片 / PDF」预览增强
//   · 作用范围**仅限右侧栏里的图片 / PDF 预览**；文本 / 代码 / 日志 / 文件列表等
//     一律交还给产品自己的滚动与滑动条，我们完全不介入（不加类、不接管滚轮）
//   · 图片 / PDF：滚轮 = 缩放（以光标为锚点）、左键拖动 = 平移、双击 = 适宽 ↔ 1:1
//   · 预览区右侧与底部使用加粗的可拖动滑动条（14px，覆盖产品的 8px 细条）
//   · 右侧栏收起 / 预览关闭 / 切换成文本类文件 → 立即解绑，原生行为完全恢复
(function () {
  if (window.__dshPreviewTools) return;
  window.__dshPreviewTools = true;

  var MIN = 0.15, MAX = 8, STEP = 0.0015, PAD = 8;
  var VP = 'dsh-pv-vp', PAN = 'dsh-pv-pan', BADGE = 'dsh-pv-badge', STYLE = 'dsh-pv-style';
  // 文本类预览的标志（产品自己的渲染器）：出现即说明这不是图片/PDF，我们不介入
  var TEXT_MARK = '[data-textpreview-plain], [data-textpreview-page], pre, [data-code-preview]';
  // 图片 / PDF 的媒体元素候选（PDF 渲染成 canvas / embed / object / img 都认）
  var MEDIA_MARK = '[data-image-preview] img, [data-image-preview] canvas, canvas, embed, object, iframe, video, img';
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

  // 把「内容」按视口像素移动 (dx, dy)——正 dx = 内容向右，正 dy = 内容向下
  // （拖动平移时内容跟着指针走；锚点缩放时用它把同一个内容点搬回光标下）。
  // CSS zoom 会改变滚动坐标与实际位移的比例，所以先滚一次量出比例，再按比例补齐残差。
  function moveContent(st, dx, dy) {
    var vp = st.vp, frame = st.frame;
    var f0 = frame.getBoundingClientRect();
    vp.scrollLeft -= dx; vp.scrollTop -= dy;
    var f1 = frame.getBoundingClientRect();
    var ax = f1.left - f0.left, ay = f1.top - f0.top;
    var sx = dx !== 0 ? ax / dx : 1, sy = dy !== 0 ? ay / dy : 1;
    var rx = dx - ax, ry = dy - ay;
    if (Math.abs(rx) > 0.5 && Math.abs(sx) > 0.01) vp.scrollLeft -= rx / sx;
    if (Math.abs(ry) > 0.5 && Math.abs(sy) > 0.01) vp.scrollTop -= ry / sy;
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

  // 把锚点（内容里的相对位置 u/v）搬回视口内的 (ox, oy)
  function anchorTo(st, u, v, ox, oy) {
    var vp = st.vp, r = vp.getBoundingClientRect(), f = st.frame.getBoundingClientRect();
    var curX = (f.left - r.left) + u * f.width;
    var curY = (f.top - r.top) + v * f.height;
    moveContent(st, ox - curX, oy - curY);
  }

  // 以光标为锚点缩放：先记下光标处对应「内容里的相对位置」，
  // 缩放后重新测量 frame 的实际几何，把同一个点搬回光标下（不依赖 zoom 的坐标语义）。
  function applyZoom(st, k, cx, cy) {
    var vp = st.vp, frame = st.frame, r = vp.getBoundingClientRect();
    k = Math.max(MIN, Math.min(MAX, k));
    var centered = (typeof cx !== 'number' || typeof cy !== 'number');
    var ox = centered ? r.width / 2 : cx - r.left;
    var oy = centered ? r.height / 2 : cy - r.top;
    var f0 = frame.getBoundingClientRect();
    var u = f0.width > 0 ? (ox - (f0.left - r.left)) / f0.width : 0.5;
    var v = f0.height > 0 ? (oy - (f0.top - r.top)) / f0.height : 0.5;
    frame.style.zoom = (Math.abs(k - 1) < 0.001) ? '' : String(k);
    st.zoom = k;
    anchorTo(st, u, v, ox, oy);
    anchorTo(st, u, v, ox, oy);   // 残差再校正一次（缩放会改变滚动/位移的比例）
    return Math.round(k * 100);
  }

  function bind(vp, media, kind) {
    if (state.has(vp)) return false;
    var st = { vp: vp, media: media, frame: media.parentElement || media, zoom: 1,
               drag: false, lx: 0, ly: 0, on: [] };
    state.set(vp, st);
    vp.classList.add(VP);
    if (media.tagName === 'IMG') media.draggable = false;

    on(vp, st, 'wheel', function (e) {
      if (e.shiftKey) return;                       // Shift+滚轮：交给浏览器做水平滚动
      if (!e.deltaY) return;
      e.preventDefault(); e.stopPropagation();
      var k = st.zoom * Math.exp(-e.deltaY * STEP);
      showBadge(vp, applyZoom(st, k, e.clientX, e.clientY) + '%');
    }, { passive: false, capture: true });

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

    if (!window.__dshPreviewHint) {
      window.__dshPreviewHint = true;
      showBadge(vp, '滚轮缩放 · 拖动平移 · 双击适宽', 2800);
    }
    post({ type: 'dsh-preview-bound', kind: kind || '', w: vp.clientWidth, h: vp.clientHeight, sw: vp.scrollWidth, sh: vp.scrollHeight });
    return true;
  }

  // 同一个预览视口里换了文件（切换标签/点开另一个文件）时，媒体元素会变，
  // 需要重新取 frame 并清掉上一份的缩放，否则缩放会作用在已废弃的节点上。
  function refresh(vp, media, kind) {
    var st = state.get(vp);
    if (!st || st.media === media) return false;
    try { if (st.frame && st.frame.style) st.frame.style.zoom = ''; } catch (e) {}
    st.media = media;
    st.frame = media.parentElement || media;
    st.zoom = 1;
    st.drag = false;
    vp.classList.remove(PAN);
    if (media.tagName === 'IMG') media.draggable = false;
    post({ type: 'dsh-preview-rebound', kind: kind || '' });
    return true;
  }

  window.addEventListener('mousemove', function (e) {
    var list = document.querySelectorAll('.' + VP);
    for (var i = 0; i < list.length; i++) {
      var st = state.get(list[i]);
      if (st && st.drag && liveState(st)) {
        moveContent(st, e.clientX - st.lx, e.clientY - st.ly);   // 内容跟着指针走
        st.lx = e.clientX; st.ly = e.clientY;
        e.preventDefault();
      }
    }
  }, true);

  window.addEventListener('mouseup', function () {
    var list = document.querySelectorAll('.' + VP);
    for (var i = 0; i < list.length; i++) {
      var st = state.get(list[i]);
      if (st && st.drag) { st.drag = false; list[i].classList.remove(PAN); }
    }
  }, true);

  // 只认右侧栏预览里的**图片 / PDF**视口：
  //   · 必须是 [data-document-preview]（预览渲染器）里的 [data-textpreview-body] 且右栏可见；
  //   · 含文本类标记（pre / [data-textpreview-plain] …）→ 文本、代码、日志，交还产品，不绑定；
  //   · 必须找到真正的媒体元素（img / canvas / embed / object / iframe / video）。
  function findViewport() {
    var bodies = document.querySelectorAll('[data-textpreview-body]');
    for (var i = 0; i < bodies.length; i++) {
      var vp = bodies[i];
      if (liveViewport(vp) !== vp) continue;
      var host = vp.closest('[data-document-preview]');
      var kind = host ? (host.getAttribute('data-document-preview') || '') : '';
      if (vp.querySelector(TEXT_MARK)) return { vp: vp, media: null, kind: kind + '#text' };
      var media = vp.querySelector(MEDIA_MARK);
      if (!media) return { vp: vp, media: null, kind: kind + '#none' };
      if (media.tagName === 'IMG' && media.naturalWidth < 240 && media.naturalHeight < 240) {
        return { vp: vp, media: null, kind: kind + '#small-img' };
      }
      if (media.tagName === 'CANVAS' && (media.width < 300 || media.height < 200)) {
        return { vp: vp, media: null, kind: kind + '#small-canvas' };
      }
      return { vp: vp, media: media, kind: kind };
    }
    return null;
  }

  function scan() {
    addStyle();
    var found = findViewport();
    var target = (found && found.media) ? found.vp : null;
    var list = document.querySelectorAll('.' + VP);
    for (var i = 0; i < list.length; i++) {
      // 右栏收起 / 预览关闭 / 换成文本类文件 / 换了视口 → 立即解绑
      if (list[i] !== target || liveViewport(list[i]) !== list[i]) unbind(list[i]);
    }
    if (target && !bind(target, found.media, found.kind)) refresh(target, found.media, found.kind);
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
