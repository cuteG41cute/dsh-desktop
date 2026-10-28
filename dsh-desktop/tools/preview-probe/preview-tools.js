// dsh-desktop 注入脚本：右侧栏「图片 / PDF」预览增强
//   · 作用范围**仅限右侧栏里的图片 / PDF 预览**；文本 / 代码 / 日志 / 文件列表等
//     一律交还给产品自己的滚动与滑动条，我们完全不介入（不加类、不接管滚轮）
//   · 图片：滚轮 = 缩放（以光标为锚点）、左键拖动 = 平移、双击 = 适宽 ↔ 1:1
//   · PDF：**Ctrl + 滚轮** = 缩放（单滚轮保持上下滑动）、左键拖动 = 平移、
//     双击 = 适宽 ↔ 100%；缩放是**全局**的（所有页一起），且可以放大到超出显示区域
//   · 预览区右侧与底部使用加粗的可拖动滑动条（14px，覆盖产品的 8px 细条）
//   · **任何**预览（图片 / PDF / 文本 / 代码 / Markdown）右键都有菜单：
//     保存到…（宿主弹 Windows 另存为对话框，默认桌面）/ 复制文件路径 / 在资源管理器中显示；
//     图片另有「复制图片」与缩放项，文本另有「复制 / 全选」（不牺牲原来的文本操作）
//   · **拖拽**：只有「右栏文件树的行」和「会话里的交付卡」能拖出去（由宿主发起原生 OLE 拖放，
//     资源管理器、桌面、聊天窗口都接得住）；文件夹落回输入框时变成一段路径文字。
//     **预览不参与拖拽** —— 预览里的左键拖动是平移手势，保存走右键菜单
//   · 右侧栏收起 / 预览关闭 / 切换成文本类文件 → 立即解绑，原生行为完全恢复
(function () {
  if (window.__dshPreviewTools) return;
  window.__dshPreviewTools = true;

  var MIN = 0.15, MAX = 8, STEP = 0.0015, PAD = 8;
  var PDF_PAGE = '[data-pdf-page]';
  var VP = 'dsh-pv-vp', PAN = 'dsh-pv-pan', BADGE = 'dsh-pv-badge', STYLE = 'dsh-pv-style';
  var MENU = 'dsh-pv-menu';
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
      '#' + BADGE + '.show{opacity:1}' +
      // 右键菜单：用产品的主题 token，深浅色都跟着走；hover 用中性叠加，不挑主题
      '#' + MENU + '{position:fixed;z-index:2147483000;min-width:216px;padding:5px;border-radius:10px;' +
      'background:var(--dsw-alias-bg-layer-1,#fff);color:var(--dsw-alias-label-primary,#1f2328);' +
      'border:1px solid var(--dsw-alias-border-l2,rgba(0,0,0,.12));' +
      'box-shadow:0 12px 32px rgba(0,0,0,.18),0 2px 6px rgba(0,0,0,.08);' +
      'font:13px/1.5 var(--dsh-font-family,system-ui,sans-serif);user-select:none}' +
      '#' + MENU + ' .dshm-mi{display:flex;align-items:center;gap:10px;width:100%;padding:7px 10px;border:0;' +
      'border-radius:6px;background:transparent;color:inherit;font:inherit;text-align:left;cursor:default}' +
      '#' + MENU + ' .dshm-mi:hover:not([disabled]),#' + MENU + ' .dshm-mi.dshm-focus:not([disabled])' +
      '{background:rgba(127,127,127,.18)}' +
      '#' + MENU + ' .dshm-mi[disabled]{opacity:.4}' +
      '#' + MENU + ' .dshm-hint{margin-left:auto;font-size:12px;color:var(--dsw-alias-label-tertiary,#8a8f98)}' +
      '#' + MENU + ' .dshm-sep{height:1px;margin:4px 8px;background:var(--dsw-alias-border-l2,rgba(0,0,0,.10))}';
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

  // ───────────────────── 拖拽：拖出去（宿主 OLE）/ 拖进来（路径文字） ─────────────────────
  // 页面拿不到「真正的文件句柄」，所以拖出去只能交给宿主：App.cs 用 CF_HDROP 起一个原生 OLE 拖放。
  // 这样资源管理器 / 桌面 / 聊天窗口都能接，落地是**复制**（只给 Copy 效果，不会把工作区里的文件搬走）。
  // 同一次拖放落回本窗口时，WebView2 会把 CF_HDROP 转成 Files 交给产品 → 变成待发送附件；
  // 文件夹不一样（目标处只拿到一个空目录条目），所以宿主同时把路径塞进 Text / text/uri-list，
  // 这里在 drop 的**捕获阶段**读到「这是目录」→ 拦下产品的附件处理、把路径写进输入框。
  var dragWatch = null;

  function dragSourceInfo(target) {
    if (!target || !target.closest) return null;
    // 1) 右栏文件树的行（文件 / 文件夹都算）
    var row = target.closest('li[data-files-entry][data-files-path]');
    if (row && row.closest('[data-sidebar-right-panel]')) {
      var p = row.getAttribute('data-files-path') || '';
      if (p) return { path: p, isDir: row.getAttribute('data-files-entry') === 'directory' };
    }
    // 2) 会话里的交付 / 文件卡片：绝对路径挂在预览按钮的 title 上
    var card = target.closest('[data-presented-file]');
    if (card) {
      var btn = card.querySelector('button[title]');
      var t = btn ? (btn.getAttribute('title') || '').trim() : '';
      if (isAbsolutePath(t)) return { path: t, isDir: false };
    }
    // 注意：**预览不是拖拽源**。预览里左键拖动是给「平移」用的（图片 / PDF 的增强手势），
    // 保存也已经有了右键菜单 —— 把它也当拖拽源会把平移抢掉，所以这里只认上面两类来源。
    return null;
  }

  function isAbsolutePath(t) {
    return !!t && (/^[A-Za-z]:[\\/]/.test(t) || t.charAt(0) === '/' || t.slice(0, 2) === '\\\\');
  }

  function stopDragWatch() {
    if (!dragWatch) return;
    document.removeEventListener('mousemove', dragWatch.move, true);
    document.removeEventListener('mouseup', dragWatch.up, true);
    dragWatch = null;
  }
  document.addEventListener('mousedown', function (e) {
    if (e.button !== 0) return;
    var info = dragSourceInfo(e.target);
    if (!info) return;
    stopDragWatch();
    var sx = e.clientX, sy = e.clientY, fired = false, el = e.target;
    var watch = {
      move: function (ev) {
        if (fired) return;
        if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) < 6) return;
        var br = webviewBridge();
        if (!br) return;                       // 浏览器里没有宿主：拖出去做不到，保持原行为
        fired = true;
        try { if (el && el.setAttribute) el.setAttribute('draggable', 'false'); } catch (e1) {}
        stopDragWatch();
        br.postMessage(JSON.stringify({
          type: 'dsh-drag-out',
          pathB64: b64utf8(info.path),
          nameB64: b64utf8(baseName(info.path)),
          isDir: !!info.isDir
        }));
      },
      up: function () { stopDragWatch(); }
    };
    dragWatch = watch;
    document.addEventListener('mousemove', watch.move, true);
    document.addEventListener('mouseup', watch.up, true);
  }, true);
  // 这些元素上的原生 HTML5 拖拽一律不要（否则浏览器自己也会起一个「拖动元素」的幽灵）
  document.addEventListener('dragstart', function (e) {
    if (dragSourceInfo(e.target)) { e.preventDefault(); e.stopPropagation(); }
  }, true);

  function dropPath(dt) {
    var t = '';
    try { t = dt.getData('text/plain') || ''; } catch (e) {}
    if (!t) {
      try {
        var uri = String(dt.getData('text/uri-list') || '').split(/\r?\n/)[0];
        t = decodeURIComponent(uri.replace(/^file:\/\/\//i, '').replace(/\//g, '\\'));
      } catch (e) {}
    }
    t = (t || '').trim();
    return isAbsolutePath(t) ? t : '';
  }
  function dropHasDirectory(dt) {
    try {
      var items = dt.items || [];
      for (var i = 0; i < items.length; i++) {
        var en = items[i].webkitGetAsEntry ? items[i].webkitGetAsEntry() : null;
        if (en && en.isDirectory) return true;
      }
    } catch (e) {}
    return false;
  }
  // 写进输入框：Lexical 认 execCommand('insertText')，这样它的内部状态也会同步
  // 写进输入框。坑：产品用的是 Lexical，它按**自己的选区**处理输入 ——
  // 光 focus() 不够（Lexical 内部没有选区 → 插不进去），得先在末尾「合成一次真实点击」，
  // 再走 execCommand('insertText')；而且它是**异步**重渲染的，插完要过一两百毫秒才看得到。
  function insertIntoComposer(txt, done) {
    var input = document.querySelector('[data-composer-input]');
    if (!input) { if (done) done(false); return; }
    try { input.focus(); } catch (e) {}
    try {
      var r = input.getBoundingClientRect();
      var opts = { bubbles: true, cancelable: true, clientX: r.right - 12, clientY: r.bottom - 12, button: 0, buttons: 1, composed: true };
      try { input.dispatchEvent(new PointerEvent('pointerdown', opts)); } catch (e) {}
      input.dispatchEvent(new MouseEvent('mousedown', opts));
      try { input.dispatchEvent(new PointerEvent('pointerup', opts)); } catch (e) {}
      input.dispatchEvent(new MouseEvent('mouseup', opts));
      input.dispatchEvent(new MouseEvent('click', opts));
      var sel = window.getSelection(), range = document.createRange();
      range.selectNodeContents(input);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    } catch (e) {}
    try { document.execCommand('insertText', false, txt); } catch (e) {}
    // 异步确认：Lexical 重渲染之后文本里应该有我们插的路径；没有就退化成「复制到剪贴板」
    setTimeout(function () {
      var ok = false;
      try { ok = (document.querySelector('[data-composer-input]').textContent || '').indexOf(txt) >= 0; } catch (e) {}
      if (!ok) {
        try { navigator.clipboard.writeText(txt); } catch (e) {}
        note('已复制文件夹路径，在输入框里 Ctrl+V 粘贴');
      }
      if (done) done(ok);
    }, 260);
  }
  function note(txt) {
    var host = document.querySelector('[data-textpreview-body]') || document.querySelector('[data-composer-card]') || document.body;
    try { showBadge(host, txt, 2200); } catch (e) {}
  }
  document.addEventListener('drop', function (e) {
    var dt = e.dataTransfer;
    if (!dt || !dropHasDirectory(dt)) return;      // 普通文件：完全交给产品（变成待发送附件）
    var p = dropPath(dt);
    e.preventDefault();
    e.stopPropagation();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    if (!p) { note('这个文件夹的路径拿不到（请从右侧文件列表拖）'); return; }
    // 注意：不能在 drop 事件里直接改 Lexical 的内容（拖放处理期间编辑命令会被忽略），
    // 挪到下一个宏任务再插 —— 实测这一步是关键。
    setTimeout(function () {
      insertIntoComposer(p, function (ok) {
        if (ok) note('已把文件夹路径写进输入框');
      });
    }, 300);
  }, true);

  // ───────────────────── 右键菜单（只认右栏里的图片预览） ─────────────────────
  // 图片预览上的右键菜单：保存到… / 复制图片 / 复制文件路径 / 适应宽度 / 实际大小 / 在资源管理器中显示。
  // 「保存」不在页面里落盘 —— 交给宿主（App.cs）弹 Windows 的另存为对话框（默认桌面），
  // 页面只负责把**原文件路径**（或退化时把图片字节）用 base64 送过去：
  // base64 只有 [A-Za-z0-9+/=]，不会被 JSON 转义搞坏（Windows 路径里的反斜杠是这里的头号坑）。
  // 文本 / 代码 / PDF 的右键菜单一律不接管（连 preventDefault 都不做）。
  var ctx = null;                  // { el, vp, items, idx }
  var reqSeq = 0, pending = {};    // requestId → { vp, name }

  function webviewBridge() {
    try {
      if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) return window.chrome.webview;
    } catch (e) {}
    return null;
  }
  function b64utf8(s) {
    var bytes = new TextEncoder().encode(String(s == null ? '' : s));
    var out = '';
    for (var i = 0; i < bytes.length; i += 4096) out += String.fromCharCode.apply(null, bytes.subarray(i, i + 4096));
    return btoa(out);
  }
  function unb64utf8(s) {
    try {
      var bin = atob(s), bytes = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return new TextDecoder().decode(bytes);
    } catch (e) { return ''; }
  }
  function baseName(p) { var at = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\')); return at < 0 ? p : p.slice(at + 1); }

  // 原文件路径：产品把完整路径写在预览头部的 title 上（.dhJKeW_path[title="C:\...\a.png"]）。
  // [data-textpreview-url] 是 dsh-resource://file/session/<sid>/<工作区相对路径>，拿不到绝对路径。
  function previewFilePath(vp) {
    var host = vp && vp.closest ? vp.closest('[data-document-preview]') : null;
    if (!host) return '';
    var nodes = host.querySelectorAll('[title]');
    for (var i = 0; i < nodes.length; i++) {
      var t = (nodes[i].getAttribute('title') || '').trim();
      if (t.length < 4 || t.length > 800) continue;
      if (/^(https?|blob|data|dsh-resource):/i.test(t)) continue;
      if (!/^[A-Za-z]:[\\/]/.test(t) && t.charAt(0) !== '/' && !/^\\\\/.test(t)) continue;
      return t;
    }
    return '';
  }
  // 预览里现在展示的是什么文件：image / pdf / text（文本、代码、日志、Markdown 都算 text）
  function previewDetailFor(vp) {
    if (!vp || liveViewport(vp) !== vp) return null;
    var img = vp.querySelector('[data-image-preview] img');
    var pdf = vp.querySelectorAll('[data-pdf-page]').length > 0;
    var kind = (img && img.naturalWidth) ? 'image' : (pdf ? 'pdf' : 'text');
    if (kind === 'text' && !(vp.textContent || '').trim() && !vp.querySelector('img, canvas')) return null;
    return { vp: vp, kind: kind, img: kind === 'image' ? img : null, pdf: kind === 'pdf', path: previewFilePath(vp) };
  }
  function detailOfTarget(target) {
    if (!target || !target.closest) return null;
    var vp = target.closest('[data-textpreview-body]');
    return vp ? previewDetailFor(vp) : null;
  }
  function currentDetail() {
    var vps = document.querySelectorAll('[data-textpreview-body]');
    for (var i = 0; i < vps.length; i++) {
      var d = previewDetailFor(vps[i]);
      if (d) return d;
    }
    return null;
  }

  function closeCtxMenu() {
    if (ctx && ctx.el && ctx.el.parentNode) ctx.el.parentNode.removeChild(ctx.el);
    ctx = null;
  }
  function menuSep() { var d = document.createElement('div'); d.className = 'dshm-sep'; return d; }
  function menuItem(ctxObj, label, hint, disabled, run) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'dshm-mi';
    b.textContent = label;
    if (hint) { var h = document.createElement('span'); h.className = 'dshm-hint'; h.textContent = hint; b.appendChild(h); }
    if (disabled) b.disabled = true;
    // 用 mousedown 阻止默认行为：菜单项不抢焦点、也不让外部 mousedown 先把菜单关掉
    b.addEventListener('mousedown', function (e) { e.preventDefault(); e.stopPropagation(); });
    b.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      closeCtxMenu();
      if (!disabled) run();
    });
    ctxObj.items.push(b);
    return b;
  }
  function openCtxMenu(detail, x, y) {
    closeCtxMenu();
    var box = document.createElement('div');
    box.id = MENU;
    box.setAttribute('role', 'menu');
    var st = state.get(detail.vp);
    var c = { el: box, vp: detail.vp, items: [], idx: -1 };
    var name = detail.path ? baseName(detail.path) : 'image.png';

    // 文本类：先给「复制 / 全选」，别让右键变成只能保存（原来的选词复制习惯要留住）
    if (detail.kind === 'text') {
      box.appendChild(menuItem(c, '复制', 'Ctrl+C', false, function () { copySelection(detail); }));
      box.appendChild(menuItem(c, '全选', 'Ctrl+A', false, function () { selectAllText(detail); }));
      box.appendChild(menuSep());
    }
    box.appendChild(menuItem(c, '保存到…', 'Ctrl+S', false, function () { saveFile(detail, name); }));
    if (detail.kind === 'image') box.appendChild(menuItem(c, '复制图片', '', false, function () { copyImage(detail); }));
    box.appendChild(menuItem(c, '复制文件路径', '', !detail.path, function () { copyPath(detail); }));
    if (st && (detail.kind === 'image' || detail.kind === 'pdf')) {
      box.appendChild(menuSep());
      if (detail.kind === 'image') {
        box.appendChild(menuItem(c, '适应宽度', '', false, function () { try { applyZoom(st, fitScale(st), x, y); } catch (e) {} }));
        box.appendChild(menuItem(c, '实际大小（100%）', '', false, function () { try { applyZoom(st, 1, x, y); } catch (e) {} }));
      } else {
        box.appendChild(menuItem(c, '适应宽度', '', false, function () { try { zoomPdfAt(st, pdfFitK(st), x, y); } catch (e) {} }));
        box.appendChild(menuItem(c, '实际大小（100%）', '', false, function () { try { zoomPdfAt(st, 1, x, y); } catch (e) {} }));
      }
    }
    box.appendChild(menuSep());
    box.appendChild(menuItem(c, '在资源管理器中显示', '', !detail.path, function () { revealFile(detail); }));

    document.body.appendChild(box);
    var r = box.getBoundingClientRect();
    box.style.left = Math.min(Math.max(6, x), Math.max(6, window.innerWidth - r.width - 6)) + 'px';
    box.style.top = Math.min(Math.max(6, y), Math.max(6, window.innerHeight - r.height - 6)) + 'px';
    ctx = c;
  }
  function moveFocus(step) {
    if (!ctx) return;
    var enabled = ctx.items.filter(function (b) { return !b.disabled; });
    if (!enabled.length) return;
    var cur = enabled.indexOf(ctx.items[ctx.idx]);
    var next = cur < 0 ? (step > 0 ? 0 : enabled.length - 1) : (cur + step + enabled.length) % enabled.length;
    if (ctx.items[ctx.idx]) ctx.items[ctx.idx].classList.remove('dshm-focus');
    ctx.idx = ctx.items.indexOf(enabled[next]);
    ctx.items[ctx.idx].classList.add('dshm-focus');
  }

  // ── 动作 ──
  function saveFile(detail, name) {
    var br = webviewBridge(), id = 'save-' + (++reqSeq);
    var msg = { type: 'dsh-save-file', requestId: id, nameB64: b64utf8(name || 'file') };
    if (br) {
      pending[id] = { vp: detail.vp };
      if (detail.path) {
        msg.pathB64 = b64utf8(detail.path);          // 常规路径：宿主直接复制原文件（逐字节一致，且不限大小）
        br.postMessage(JSON.stringify(msg));
        return;
      }
      // 万一取不到原文件路径：只有图片能从 blob 拿到字节（32MB 上限），其它类型直接说明
      if (!detail.img) { delete pending[id]; showBadge(detail.vp, '拿不到这个文件的原路径，无法保存', 2800); return; }
      fetch(detail.img.currentSrc || detail.img.src)
        .then(function (r) { return r.blob(); })
        .then(function (blob) {
          if (blob.size > 32 * 1024 * 1024) { delete pending[id]; showBadge(detail.vp, '图片太大，无法用这种方式保存', 2600); return; }
          return blob.arrayBuffer().then(function (buf) {
            var bytes = new Uint8Array(buf), out = '';
            for (var i = 0; i < bytes.length; i += 4096) out += String.fromCharCode.apply(null, bytes.subarray(i, i + 4096));
            msg.data = btoa(out);
            br.postMessage(JSON.stringify(msg));
          });
        })
        .catch(function () { delete pending[id]; showBadge(detail.vp, '保存失败：读取图片失败', 2600); });
      return;
    }
    // 普通浏览器（没有宿主）：图片退回 <a download>；其它类型没有可下载的 blob，直接说明
    if (!detail.img) { showBadge(detail.vp, '要在桌面窗口里才能保存这个文件（浏览器里没有宿主）', 2800); return; }
    var a = document.createElement('a');
    a.href = detail.img.currentSrc || detail.img.src;
    a.download = name || 'image.png';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  function copyImage(detail) {
    var br = webviewBridge();
    if (br && detail.path) {
      var id = 'copy-' + (++reqSeq);
      pending[id] = { vp: detail.vp };
      br.postMessage(JSON.stringify({ type: 'dsh-copy-image', requestId: id, pathB64: b64utf8(detail.path) }));
      return;
    }
    if (!navigator.clipboard || !window.ClipboardItem) { showBadge(detail.vp, '这个环境不支持复制图片', 2200); return; }
    fetch(detail.img.currentSrc || detail.img.src)
      .then(function (r) { return r.blob(); })
      .then(function (blob) {
        var item = {};
        item[blob.type || 'image/png'] = blob;
        return navigator.clipboard.write([new ClipboardItem(item)]);
      })
      .then(function () { showBadge(detail.vp, '已复制图片', 1400); })
      .catch(function () { showBadge(detail.vp, '复制图片失败', 2200); });
  }
  function copySelection(detail) {
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) {}
    showBadge(detail.vp, ok ? '已复制选中内容' : '没有选中内容', 1600);
  }
  function selectAllText(detail) {
    try {
      var sel = window.getSelection(), range = document.createRange();
      range.selectNodeContents(detail.vp);
      sel.removeAllRanges(); sel.addRange(range);
      showBadge(detail.vp, '已全选', 1200);
    } catch (e) {}
  }
  function copyPath(detail) {
    if (!detail.path) return;
    var done = function () { showBadge(detail.vp, '已复制文件路径', 1400); };
    var fail = function () { showBadge(detail.vp, '复制失败', 2000); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(detail.path).then(done, fail);
      return;
    }
    try {
      var ta = document.createElement('textarea');
      ta.value = detail.path;
      ta.style.cssText = 'position:fixed;opacity:0;left:-9999px';
      document.body.appendChild(ta); ta.select();
      document.execCommand('copy') ? done() : fail();
      ta.remove();
    } catch (e) { fail(); }
  }
  function revealFile(detail) {
    if (!detail.path) return;
    var br = webviewBridge();
    if (!br) { showBadge(detail.vp, '只能在桌面窗口里打开所在文件夹', 2400); return; }
    br.postMessage(JSON.stringify({ type: 'dsh-reveal', pathB64: b64utf8(detail.path) }));
  }

  // ── 宿主回执 ──
  function onHostMessage(e) {
    var m = e && e.data;
    if (typeof m === 'string') { try { m = JSON.parse(m); } catch (err) { return; } }
    if (!m || typeof m !== 'object') return;
    var p = pending[m.requestId] || null;
    if (p) delete pending[m.requestId];
    var vp = p && p.vp && p.vp.isConnected ? p.vp : document.querySelector('[data-textpreview-body]');
    if (!vp) return;
    if (m.type === 'dsh-save-file-result') {
      if (m.ok) {
        var saved = m.pathB64 ? unb64utf8(m.pathB64) : '';
        showBadge(vp, saved ? '已保存：' + saved : '已保存', 3000);
      } else if (m.reason === 'cancelled') {
        showBadge(vp, '已取消保存', 1200);
      } else {
        showBadge(vp, '保存失败：' + (m.messageB64 ? unb64utf8(m.messageB64) : (m.message || '未知错误')), 3000);
      }
    } else if (m.type === 'dsh-copy-image-result') {
      showBadge(vp, m.ok ? '已复制图片' : '复制图片失败', 1500);
    }
  }
  if (webviewBridge()) {
    try { window.chrome.webview.addEventListener('message', onHostMessage); } catch (e) {}
  }

  // ── 触发与关闭 ──
  document.addEventListener('contextmenu', function (e) {
    var t = e.target;
    // 可编辑 / 链接 / 表单控件：原生菜单更有用（粘贴、复制链接…），不抢
    if (t && t.closest && t.closest('a, input, textarea, select, [contenteditable="true"]')) { closeCtxMenu(); return; }
    var detail = detailOfTarget(t);
    if (!detail) { closeCtxMenu(); return; }      // 不在右栏预览里：完全交给产品
    e.preventDefault();
    e.stopPropagation();
    openCtxMenu(detail, e.clientX, e.clientY);
  }, true);
  document.addEventListener('mousedown', function (e) {
    if (ctx && !(ctx.el && ctx.el.contains(e.target))) closeCtxMenu();
  }, true);
  document.addEventListener('keydown', function (e) {
    if (ctx) {
      if (e.key === 'Escape') { closeCtxMenu(); e.preventDefault(); e.stopPropagation(); return; }
      if (e.key === 'ArrowDown') { moveFocus(1); e.preventDefault(); e.stopPropagation(); return; }
      if (e.key === 'ArrowUp') { moveFocus(-1); e.preventDefault(); e.stopPropagation(); return; }
      if (e.key === 'Enter' && ctx.idx >= 0 && ctx.items[ctx.idx]) { ctx.items[ctx.idx].click(); e.preventDefault(); return; }
    }
    // 图片预览里的 Ctrl+S = 保存到…（焦点在输入框里时不抢）
    if (e.ctrlKey || e.metaKey) {
      var el = document.activeElement;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (String(e.key).toLowerCase() !== 's') return;
      var detail = currentDetail();
      if (!detail) return;
      e.preventDefault(); e.stopPropagation();
      saveFile(detail, detail.path ? baseName(detail.path) : (detail.kind === 'image' ? 'image.png' : 'file'));
    }
  }, true);
  window.addEventListener('blur', closeCtxMenu);
  window.addEventListener('resize', function () { closeCtxMenu(); }, true);
  document.addEventListener('scroll', function () { if (ctx) closeCtxMenu(); }, true);
  document.addEventListener('wheel', function () { if (ctx) closeCtxMenu(); }, true);

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
    if (ctx && (!ctx.vp || !ctx.vp.isConnected || liveViewport(ctx.vp) !== ctx.vp)) closeCtxMenu();
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
