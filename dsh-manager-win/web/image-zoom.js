// dsh-manager 自己的图片预览缩放（不依赖产品那套 zoom 变量）
// 产品当前实现：.JFRUHG_surface 上 style="zoom: 8; --document-zoom-width: 2048px"
// 而且 width 会随 zoom 反向缩小 → 净效果恒等于「适宽」，所以放大看不到变化。
// 这里直接接管：把 surface 的 zoom 干掉、改成按像素宽度布局，滚动交给 .dsh-pv-vp。
(function () {
  if (window.__dshImgZoom) return;
  window.__dshImgZoom = true;

  var MIN = 0.1, MAX = 12, STEP = 1.0022;
  var zoom = 1;            // 相对「适宽」
  var baseW = 0, baseH = 0;
  var bound = null;
  var dragging = false, sx = 0, sy = 0, sl = 0, st = 0;

  function q(sel, root) { try { return (root || document).querySelector(sel); } catch (e) { return null; } }
  function isPdf() { return !!q('[data-pdf-page]'); }
  function surface() { return q('div[class*="_surface"]'); }
  function pane() { return q('.dsh-pv-vp') || q('div[class*="_scrollport"]'); }
  function img() { var s = surface(); return s ? s.querySelector('img') : null; }

  function measure() {
    var s = surface(), i = img();
    if (!s || !i) return false;
    // 基线 = 图片自身像素尺寸（产品适宽时的自然宽度）
    if (!i.naturalWidth) return false;
    baseW = i.naturalWidth; baseH = i.naturalHeight;
    return true;
  }

  function apply() {
    var s = surface(), i = img();
    if (!s || !i || !baseW) return;
    s.style.zoom = '1';
    s.style.transform = 'none';
    s.style.width = Math.round(baseW * zoom) + 'px';
    i.style.width = '100%';
    i.style.height = 'auto';
    i.style.maxWidth = 'none';
    i.style.maxHeight = 'none';
    var b = document.getElementById('dsh-pv-badge');
    if (b) b.textContent = Math.round(zoom * 100) + '%';
  }

  function reset() { zoom = 1; apply(); }

  function onWheel(e) {
    var s = surface();
    if (!s || !img() || isPdf()) return;   // PDF 交给原来的脚本
    if (!measure()) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();

    var p = pane();
    var rect = p ? p.getBoundingClientRect() : s.getBoundingClientRect();
    var cx = e.clientX - rect.left, cy = e.clientY - rect.top;
    var px = p ? p.scrollLeft : 0, py = p ? p.scrollTop : 0;
    var oldW = baseW * zoom;

    var next = zoom * Math.pow(STEP, -e.deltaY);
    next = Math.max(MIN, Math.min(MAX, next));
    if (next === zoom) return;
    zoom = next;
    apply();

    // 以光标为锚：缩放前后同一处内容位置不变
    if (p && oldW > 0) {
      var k = (baseW * zoom) / oldW;
      p.scrollLeft = (px + cx) * k - cx;
      p.scrollTop = (py + cy) * k - cy;
    }
  }

  function onDown(e) {
    if (e.button !== 0) return;
    var s = surface();
    if (!s || !img() || isPdf()) return;
    var p = pane();
    if (!p) return;
    dragging = true; sx = e.clientX; sy = e.clientY; sl = p.scrollLeft; st = p.scrollTop;
    p.style.cursor = 'grabbing';
    e.preventDefault();
  }
  function onMove(e) {
    if (!dragging) return;
    var p = pane();
    if (!p) return;
    p.scrollLeft = sl - (e.clientX - sx);
    p.scrollTop = st - (e.clientY - sy);
    e.preventDefault();
  }
  function onUp() {
    if (!dragging) return;
    dragging = false;
    var p = pane();
    if (p) p.style.cursor = '';
  }

  document.addEventListener('wheel', onWheel, { capture: true, passive: false });
  document.addEventListener('mousedown', onDown, true);
  document.addEventListener('mousemove', onMove, true);
  document.addEventListener('mouseup', onUp, true);
  document.addEventListener('dblclick', function (e) {
    var s = surface();
    if (!s || !img() || isPdf()) return;
    e.preventDefault();
    e.stopPropagation();
    reset();
  }, true);
})();
