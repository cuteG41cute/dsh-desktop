// dsh-desktop 注入脚本：右侧栏「图片 / PDF」预览增强
//   · 作用范围**仅限右侧栏里的图片 / PDF 预览**；文本 / 代码 / 日志 / 文件列表等
//     一律交还给产品自己的滚动与滑动条，我们完全不介入（不加类、不接管滚轮）
//   · 图片：滚轮 = 缩放（以光标为锚点）、左键拖动 = 平移、双击 = 适宽 ↔ 1:1
//   · PDF：**Ctrl + 滚轮** = 缩放（单滚轮保持上下滑动）、左键拖动 = 平移、
//     双击 = 适宽 ↔ 100%；缩放是**全局**的（所有页一起），且可以放大到超出显示区域
//   · 预览区右侧与底部使用加粗的可拖动滑动条（14px，覆盖产品的 8px 细条）
//   · 右侧栏收起 / 预览关闭 / 切换成文本类文件 → 立即解绑，原生行为完全恢复
(function () {
  if (window.__dshPreviewTools) return;
  window.__dshPreviewTools = true;

  var MIN = 0.15, MAX = 8, STEP = 0.0015, PAD = 8;
  var PDF_PAGE = '[data-pdf-page]';
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
      try { if (st.pdf) { pdfClear(st); pdfReclip(st); } } catch (e) {}
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

  // ───────────────────────── PDF：全局缩放（不用 CSS zoom） ─────────────────────────
  // 产品把 PDF 每一页渲染成 <div data-pdf-page><canvas>，画布宽度是
  // width:min(var(--pdf-page-width), 100%)，而页容器与正文容器都带 overflow-x:hidden。
  // 于是图片那套 frame.style.zoom 在 PDF 上有三个硬伤：
  //   ① frame 只是**第一页**的容器 → 只放大第一页；
  //   ② 画布宽度是百分比，CSS zoom 会连它一起缩掉（数字涨到几百，画面反而缩回一屏）；
  //   ③ overflow-x:hidden → 超出的部分被裁掉，根本滚不到。
  // 这里改走「按页写绝对像素宽度」：canvas 宽度 = 页面自然宽度(--pdf-page-width) × k，
  // 并把页 / 正文容器的 overflow 临时放开，让 [data-textpreview-body] 自己去滚。
  // k 以**页面 100%（96dpi 原始尺寸）**为基准，所以 100% 就是真正的 1:1。
  function pdfNodes(vp) {
    var pages = vp.querySelectorAll(PDF_PAGE);
    var canvases = [];
    for (var i = 0; i < pages.length; i++) {
      var c = pages[i].querySelector('canvas');
      if (c) canvases.push(c);
    }
    return canvases.length ? { pages: pages, canvases: canvases, natural: [] } : null;
  }
  function pdfNatural(canvas) {
    var raw = '';
    try { raw = canvas.style.getPropertyValue('--pdf-page-width') || ''; } catch (e) {}
    var n = parseFloat(raw);
    return (n > 40) ? n : 0;
  }
  function pdfUnclip(st) {          // 放开中间容器的裁剪（记下原内联值，解绑时逐字还原）
    for (var i = 0; i < st.pdf.pages.length; i++) {
      var el = st.pdf.pages[i];
      while (el && el !== st.vp && el.nodeType === 1) {
        if (st.unclipped.indexOf(el) < 0) {
          st.unclipped.push(el);
          el.setAttribute('data-dsh-pv-overflow', el.style.overflow || '');
          el.style.overflow = 'visible';
        }
        el = el.parentElement;
      }
    }
  }
  function pdfReclip(st) {
    for (var i = 0; i < st.unclipped.length; i++) {
      var el = st.unclipped[i];
      var prev = el.getAttribute('data-dsh-pv-overflow') || '';
      if (prev) el.style.overflow = prev; else el.style.removeProperty('overflow');
      el.removeAttribute('data-dsh-pv-overflow');
    }
    st.unclipped = [];
  }
  function pdfClear(st) {           // 交还产品自己的响应式宽度
    for (var i = 0; i < st.pdf.canvases.length; i++) {
      var c = st.pdf.canvases[i];
      c.style.removeProperty('width');
      c.style.removeProperty('max-width');
      c.style.removeProperty('height');
    }
  }
  function pdfApply(st, k) {
    for (var i = 0; i < st.pdf.canvases.length; i++) {
      var node = st.pdf.canvases[i];
      var nat = st.pdf.natural[i] || 0;
      if (!nat) { node.style.removeProperty('width'); node.style.removeProperty('max-width'); continue; }
      node.style.maxWidth = 'none';
      node.style.height = 'auto';
      node.style.width = Math.round(nat * k * 100) / 100 + 'px';
    }
    st.zoom = k;
  }
  function pdfNaturalWidths(st) {   // 采集每页自然宽度（产品渲染时写在画布上的 --pdf-page-width）
    var list = [];
    for (var i = 0; i < st.pdf.canvases.length; i++) {
      var nat = pdfNatural(st.pdf.canvases[i]);
      if (!nat && i === 0) {
        // 只有第一页值得兜底（绑定条件就要求它已经渲染出尺寸）：万一产品不再写
        // --pdf-page-width，就用「当前宽度 ÷ 当前倍率」反推。
        var cur = st.pdf.canvases[i].getBoundingClientRect().width;
        nat = (cur > 0 && st.zoom > 0) ? cur / st.zoom : 0;
      }
      // 后面的页是产品**滚动到位才渲染**的：这时它还没有 --pdf-page-width，
      // 绝对不要去猜尺寸（默认画布 300px 会把该页定成另一个比例）——
      // 记 0，等它渲染出来再由 pdfKeepUp 按同一个倍率补上。
      list.push(nat);
    }
    st.pdf.natural = list;
    return list;
  }
  // 画布真正能用的宽度 = **页面容器的内容宽**（视口宽 − 正文容器内边距 − 页容器内边距）。
  // 不能拿「视口宽 − 一个估计值」凑：产品那两层容器还有 8px + 12px 的内边距，
  // 少算就会让「适宽」反而宽出几十像素、多出一条横向滚动条。
  function pdfAvailable(st) {
    var c = st.pdf.canvases[0];
    var host = c && c.parentElement;
    if (host) {
      var cs = getComputedStyle(host);
      var pad = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
      var w = host.clientWidth - pad;
      if (w > 40) return w;
    }
    return Math.max(40, st.vp.clientWidth - PAD * 2);
  }
  function pdfFitK(st) {            // 适宽：第一页正好铺满可用宽度（不留横向滚动条）
    var nat = st.pdf.natural[0] || 0;
    if (!nat) return st.zoom;
    return Math.max(MIN, Math.min(MAX, pdfAvailable(st) / nat));
  }
  function pdfBaseK(st) {           // 产品默认布局（未覆盖宽度）对应的倍率
    var nat = st.pdf.natural[0] || 0;
    if (!nat) return 1;
    var w = 0;
    for (var i = 0; i < st.pdf.canvases.length; i++) {
      var r = st.pdf.canvases[i].getBoundingClientRect();
      if (r.width > w) w = r.width;
    }
    return w > 0 ? w / nat : 1;
  }
  function pdfIsFit(st) {
    return Math.abs(st.zoom - pdfFitK(st)) < 0.02;
  }
  // 以光标为锚点缩放：内容尺寸与 k 成正比，所以按「光标处的相对坐标」换算滚动位置 ——
  // 缩放前后各量一次，不依赖任何关于内边距 / 居中方式的假设。
  function zoomPdfAt(st, k, cx, cy) {
    k = Math.max(MIN, Math.min(MAX, k));
    st.pdfZoomed = true;            // 从这里开始才由我们接管宽度
    var vp = st.vp, r = vp.getBoundingClientRect();
    var px = (typeof cx === 'number') ? cx - r.left : r.width / 2;
    var py = (typeof cy === 'number') ? cy - r.top : r.height / 2;
    var c0 = st.pdf.canvases[0].getBoundingClientRect();
    var ox0 = (c0.left - r.left) + vp.scrollLeft, oy0 = (c0.top - r.top) + vp.scrollTop;
    var w0 = c0.width || 1, h0 = c0.height || 1;
    var tx = (vp.scrollLeft + px - ox0) / w0, ty = (vp.scrollTop + py - oy0) / h0;
    pdfApply(st, k);
    var c1 = st.pdf.canvases[0].getBoundingClientRect();   // getBoundingClientRect 会先刷新布局
    var ox1 = (c1.left - r.left) + vp.scrollLeft, oy1 = (c1.top - r.top) + vp.scrollTop;
    vp.scrollLeft = ox1 + tx * (c1.width || 1) - px;
    vp.scrollTop = oy1 + ty * (c1.height || 1) - py;
    return Math.round(k * 100);
  }
  function setupPdf(st, vp) {       // 绑定 / 换文件 / 尺寸变化后重建 PDF 状态
    var pdf = pdfNodes(vp);
    st.pdf = pdf;
    if (!pdf) return false;
    st.frame = pdf.pages[0];        // 拖动平移只需要一个几何参照
    st.zoom = 1;
    st.pdfZoomed = false;           // 用户还没缩放时，绝不去写内联宽度（保持产品自己的响应式排版）
    pdfNaturalWidths(st);
    pdfUnclip(st);
    st.zoom = pdfBaseK(st);         // 产品默认排出来的倍率（窄面板≈适宽，宽面板＝1:1）
    return true;
  }
  // 后几页渲染完成（画布拿到 --pdf-page-width）后按**同一个倍率**补齐，
  // 否则放大状态下滚动出来的新页会是另一个尺寸。
  function pdfKeepUp(st) {
    var fresh = pdfNodes(st.vp);
    if (!fresh) return false;
    var beforeCount = st.pdf.canvases.length;
    var beforeNat = st.pdf.natural.join(',');
    st.pdf.pages = fresh.pages;
    st.pdf.canvases = fresh.canvases;
    pdfReclip(st);
    pdfUnclip(st);
    pdfNaturalWidths(st);
    var changed = st.pdf.canvases.length !== beforeCount || st.pdf.natural.join(',') !== beforeNat;
    // 只有用户已经在缩放，才需要把新渲染出来的页按当前倍率补齐；
    // 否则产品自己的响应式排版更准，我们什么都不该写。
    if (changed && st.pdfZoomed) { pdfApply(st, st.zoom); return true; }
    return false;
  }
  function bind(vp, media, kind) {
    if (state.has(vp)) return false;
    var st = { vp: vp, media: media, frame: media.parentElement || media, zoom: 1,
               drag: false, lx: 0, ly: 0, on: [], pdf: null, unclipped: [] };
    setupPdf(st, vp);                             // PDF 走独立分支（不是 PDF 时 st.pdf = null）
    state.set(vp, st);
    vp.classList.add(VP);
    if (media.tagName === 'IMG') media.draggable = false;

    on(vp, st, 'wheel', function (e) {
      if (e.shiftKey) return;                       // Shift+滚轮：交给浏览器做水平滚动
      if (!e.deltaY) return;
      // PDF：必须 Ctrl + 滚轮才缩放；单滚轮交还给产品做上下滑动
      // （否则一次手势既缩放又滑动，而且缩放还会带着滚动位置一起跑）
      if (st.pdf && !e.ctrlKey) return;
      e.preventDefault(); e.stopPropagation();
      var k = st.zoom * Math.exp(-e.deltaY * STEP);
      var pct = st.pdf ? zoomPdfAt(st, k, e.clientX, e.clientY) : applyZoom(st, k, e.clientX, e.clientY);
      showBadge(vp, pct + '%');
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
      if (st.pdf) {
        var fitPdf = pdfFitK(st);
        var toPdf = pdfIsFit(st) ? 1 : fitPdf;     // 适宽 ↔ 100%（1:1）
        showBadge(vp, (toPdf === 1 ? '1:1 · ' : '适宽 · ') + zoomPdfAt(st, toPdf, e.clientX, e.clientY) + '%');
        return;
      }
      var fit = fitScale(st);
      var target = Math.abs(st.zoom - fit) < 0.02 ? 1 : fit;
      showBadge(vp, (target === 1 ? '1:1 · ' : '适宽 · ') + applyZoom(st, target, e.clientX, e.clientY) + '%');
    }, true);

    if (!window.__dshPreviewHint) {
      window.__dshPreviewHint = true;
      showBadge(vp, st.pdf ? 'Ctrl+滚轮缩放 · 拖动平移 · 双击适宽/1:1' : '滚轮缩放 · 拖动平移 · 双击适宽', 2800);
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
    try { if (st.pdf) { pdfClear(st); pdfReclip(st); } } catch (e) {}
    st.media = media;
    st.frame = media.parentElement || media;
    st.zoom = 1;
    st.drag = false;
    vp.classList.remove(PAN);
    if (media.tagName === 'IMG') media.draggable = false;
    setupPdf(st, vp);              // PDF ↔ 图片互切 / 换另一个 PDF：重建尺寸状态
    post({ type: 'dsh-preview-rebound', kind: kind || '' });
    return true;
  }

  // 面板宽度变了：PDF 的宽度本来由产品 CSS 决定，我们写了绝对像素后会把它冻住 ——
  // 所以尺寸变化时先把宽度交还产品、量准自然宽度，再按当前倍率写回去
  //（当时处于「适宽」就继续保持适宽）。图片用的是 CSS zoom，不受影响。
  window.addEventListener('resize', function () {
    var list = document.querySelectorAll('.' + VP);
    for (var i = 0; i < list.length; i++) {
      var st = state.get(list[i]);
      if (!st || !st.pdf || !st.pdfZoomed || !liveState(st)) continue;
      try {
        var wasFit = pdfIsFit(st);
        pdfClear(st);
        pdfNaturalWidths(st);
        st.zoom = wasFit ? pdfFitK(st) : st.zoom;
        pdfApply(st, st.zoom);
      } catch (e) {}
    }
  }, true);

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
      var pdf = pdfNodes(vp);
      if (pdf) return { vp: vp, media: pdf.canvases[0], kind: kind + '#pdf' };
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
    if (target && found.kind.indexOf('#pdf') >= 0) {
      var bound = state.get(target);
      if (bound && bound.pdf && liveState(bound)) { try { pdfKeepUp(bound); } catch (e) {} }
    }
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
