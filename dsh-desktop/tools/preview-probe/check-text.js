// 文本/代码预览的行为核查：普通滚轮保持原生滚动；Ctrl+滚轮缩放
const out = {};
const pre = [...document.querySelectorAll('pre, [data-code-preview]')].pop();
out.foundCode = !!pre;
if (!pre) return out;
let vp = pre.parentElement, g = 0;
while (vp && g++ < 15) {
  const c = getComputedStyle(vp);
  if (/(auto|scroll)/.test(c.overflowX + c.overflowY) && vp.clientHeight > 80) break;
  vp = vp.parentElement;
}
out.vpCls = vp ? (vp.className || '').toString().slice(0, 50) : null;
out.vpBound = vp ? vp.classList.contains('dsh-pv-vp') : false;
out.barSize = vp ? (vp.offsetWidth - vp.clientWidth) + 'x' + (vp.offsetHeight - vp.clientHeight) : null;
out.scrollSize = vp ? vp.scrollWidth + 'x' + vp.clientHeight + ' (client) / ' + vp.scrollHeight + ' (scrollH)' : null;
const frame = pre.parentElement;
out.zoomInlineBefore = frame ? frame.style.zoom || '(none)' : null;
if (vp) {
  const r = vp.getBoundingClientRect();
  // 1) 普通滚轮：期望不被拦截（页面正常滚动）
  const e1 = new WheelEvent('wheel', { deltaY: 120, clientX: r.left + 50, clientY: r.top + 50, bubbles: true, cancelable: true });
  vp.dispatchEvent(e1);
  out.plainWheelPrevented = e1.defaultPrevented;
  // 2) Ctrl+滚轮：期望被拦截并缩放
  const e2 = new WheelEvent('wheel', { deltaY: -120, ctrlKey: true, clientX: r.left + 50, clientY: r.top + 50, bubbles: true, cancelable: true });
  vp.dispatchEvent(e2);
  out.ctrlWheelPrevented = e2.defaultPrevented;
  out.zoomInlineAfterCtrl = frame ? frame.style.zoom || '(none)' : null;
  out.badgeText = (document.getElementById('dsh-pv-badge') || {}).textContent || null;
  // 3) 左键拖动：文本预览不应启动平移（保留选字）
  const before = { sl: vp.scrollLeft, st: vp.scrollTop };
  vp.dispatchEvent(new MouseEvent('mousedown', { button: 0, clientX: r.left + 60, clientY: r.top + 60, bubbles: true, cancelable: true }));
  window.dispatchEvent(new MouseEvent('mousemove', { button: 0, clientX: r.left + 20, clientY: r.top + 20, bubbles: true }));
  window.dispatchEvent(new MouseEvent('mouseup', { button: 0, clientX: r.left + 20, clientY: r.top + 20, bubbles: true }));
  out.dragMovedScroll = { before, after: { sl: vp.scrollLeft, st: vp.scrollTop } };
  out.panClassDuringDrag = vp.classList.contains('dsh-pv-pan');
}
return out;
