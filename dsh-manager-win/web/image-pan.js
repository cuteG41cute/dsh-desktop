// dsh-manager：给官方缩放补「拖动平移」。
// 只做一件事：在右栏预览的滚动容器里按住左键拖动 = 平移（改 scrollLeft/scrollTop）。
// 不碰 wheel、不碰官方 zoom；未放大（没有可滚动空间）时完全不介入。
(function () {
  if (window.__dshPan) return;
  window.__dshPan = true;

  var panning = false, start = null, box = null, moved = false;

  function viewportOf(el) {
    // 从事件目标往上找「预览视口」：.rIfSMq_scrollport（产品结构）
    var n = el;
    for (var i = 0; n && i < 12; i++) {
      if (n.className && String(n.className).indexOf('_scrollport') >= 0) return n;
      n = n.parentElement;
    }
    return null;
  }

  function scrollable(vp) {
    return vp && (vp.scrollWidth > vp.clientWidth + 2 || vp.scrollHeight > vp.clientHeight + 2);
  }

  function inPreview(el) {
    // 只在预览里生效：祖先里要有 surface/frame 那套类名
    var n = el;
    for (var i = 0; n && i < 14; i++) {
      var c = n.className ? String(n.className) : '';
      if (c.indexOf('_surface') >= 0 || c.indexOf('_preview') >= 0) return true;
      n = n.parentElement;
    }
    return false;
  }

  document.addEventListener('pointerdown', function (e) {
    if (e.button !== 0) return;
    if (!inPreview(e.target)) return;
    var vp = viewportOf(e.target);
    if (!scrollable(vp)) return;             // 没放大 → 不接管
    panning = true; moved = false; box = vp;
    start = { x: e.clientX, y: e.clientY, l: vp.scrollLeft, t: vp.scrollTop };
    vp.style.cursor = 'grabbing';
    try { e.target.setPointerCapture && e.target.setPointerCapture(e.pointerId); } catch (err) {}
    e.preventDefault();                       // 阻止图片原生拖拽 / 选中文字
  }, true);

  document.addEventListener('pointermove', function (e) {
    if (!panning || !box) return;
    var dx = e.clientX - start.x, dy = e.clientY - start.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
    box.scrollLeft = start.l - dx;
    box.scrollTop = start.t - dy;
    e.preventDefault();
  }, true);

  function endPan(e) {
    if (!panning) return;
    panning = false;
    if (box) box.style.cursor = '';
    box = null;
    if (moved) {                              // 拖过之后，吃掉这次 click，避免误触关闭/打开
      var swallow = function (ev) { ev.stopPropagation(); ev.preventDefault(); };
      document.addEventListener('click', swallow, { capture: true, once: true });
      setTimeout(function () { document.removeEventListener('click', swallow, true); }, 0);
    }
  }
  document.addEventListener('pointerup', endPan, true);
  document.addEventListener('pointercancel', endPan, true);

  // 预览里的图片不允许原生 HTML5 拖拽（否则拖动会变成拖一张图出去）
  document.addEventListener('dragstart', function (e) {
    if (inPreview(e.target)) e.preventDefault();
  }, true);
})();
