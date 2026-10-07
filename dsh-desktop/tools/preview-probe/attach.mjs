// 附着到正在运行的 DSH Desktop 窗口（WebView2 远程调试），验证预览增强是否在真实窗口里生效。
// 用法：node attach.mjs [--port 9340] [--steps "dsh-mobile-app,assets,icon-foreground.png"]
import { writeFileSync } from 'node:fs';

const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const PORT = Number(opt('--port', 9340));
const PLAN = opt('--steps', 'dsh-mobile-app,assets,icon-foreground.png').split(',').filter(Boolean);
const SHOT = opt('--shot', '');

class Cdp {
  constructor(ws) { this.ws = ws; this.id = 0; this.waiting = new Map(); }
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('ws error')); });
    const c = new Cdp(ws);
    ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && c.waiting.has(m.id)) { const w = c.waiting.get(m.id); c.waiting.delete(m.id); m.error ? w.rej(new Error(JSON.stringify(m.error))) : w.res(m.result); } };
    return c;
  }
  send(method, params = {}) { const id = ++this.id; return new Promise((res, rej) => { this.waiting.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval failed');
    return r.result.value;
  }
  async shot(p) { const r = await this.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(p, Buffer.from(r.data, 'base64')); }
  async clickAt(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1, buttons: 1 });
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1, buttons: 0 });
  }
  async wheelAt(x, y, deltaY) { await this.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x, y, deltaX: 0, deltaY, pointerType: 'mouse' }); }
  async drag(x1, y1, x2, y2) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: x1, y: y1, button: 'left', clickCount: 1, buttons: 1 });
    for (let i = 1; i <= 5; i++) {
      await this.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x1 + (x2 - x1) * i / 5, y: y1 + (y2 - y1) * i / 5, button: 'left', buttons: 1 });
      await new Promise((r) => setTimeout(r, 40));
    }
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: x2, y: y2, button: 'left', clickCount: 1, buttons: 0 });
  }
  close() { try { this.ws.close(); } catch {} }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const LIST_JS = `(() => {
  const btn = [...document.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '') === '收起右侧边栏');
  let panel = btn; for (let i = 0; i < 4 && panel; i++) panel = panel.parentElement;
  if (!panel) return [];
  return [...panel.querySelectorAll('li, [role="treeitem"], [role="option"]')].map(el => {
    const r = el.getBoundingClientRect();
    return { text: (el.textContent || '').trim().slice(0, 40), x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width) };
  }).filter(r => r.text && r.w > 40);
})()`;

const MEASURE = `(() => {
  const img = [...document.querySelectorAll('img')].filter(i => i.naturalWidth >= 240).pop();
  if (!img) return { noImage: true };
  let vp = img.parentElement, g = 0;
  while (vp && g++ < 15) { const c = getComputedStyle(vp); if (/(auto|scroll)/.test(c.overflowX + c.overflowY) && vp.clientHeight > 80) break; vp = vp.parentElement; }
  const r = img.getBoundingClientRect();
  const vr = vp.getBoundingClientRect();
  return {
    bound: vp.classList.contains('dsh-pv-vp'),
    bar: (vp.offsetWidth - vp.clientWidth) + 'x' + (vp.offsetHeight - vp.clientHeight),
    zoomApplied: (img.parentElement.style.zoom || '(none)'),
    natural: img.naturalWidth + 'x' + img.naturalHeight,
    renderedPx: Math.round(r.width) + 'x' + Math.round(r.height),
    client: vp.clientWidth + 'x' + vp.clientHeight, scroll: vp.scrollWidth + 'x' + vp.scrollHeight,
    at: { x: Math.round(Math.max(vr.left + 30, Math.min(r.left + 100, vr.right - 30))), y: Math.round(Math.max(vr.top + 30, Math.min(r.top + 100, vr.bottom - 30))) },
    scrollPos: { sl: vp.scrollLeft, st: vp.scrollTop },
  };
})()`;

async function main() {
  const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
  const page = list.find((t) => t.type === 'page');
  if (!page) throw new Error('没有可附着的页面');
  const cdp = await Cdp.connect(page.webSocketDebuggerUrl);
  console.log('附着到窗口:', page.title);

  // 打开「工作区文件」标签
  console.log('打开文件标签:', await cdp.eval(`(() => {
    const btn = [...document.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '') === '收起右侧边栏');
    if (!btn) return '右栏已收起，先展开';
    let panel = btn; for (let i = 0; i < 4 && panel; i++) panel = panel.parentElement;
    const nt = [...panel.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '') === '新标签页');
    if (nt) { nt.click(); return new Promise(res => setTimeout(() => {
      const e = [...panel.querySelectorAll('button')].find(b => (b.textContent || '').trim().startsWith('工作区文件'));
      if (e) e.click();
      res(e ? '已打开' : '已有标签');
    }, 700)); }
    return '已有标签';
  })()`));
  await sleep(1800);

  for (const step of PLAN) {
    const rows = await cdp.eval(LIST_JS);
    const row = rows.find((r) => r.text === step) || rows.find((r) => r.text.includes(step));
    if (!row) { console.log('未找到', step, '候选:', rows.map((r) => r.text).slice(0, 8)); break; }
    await cdp.clickAt(row.x, row.y);
    console.log('点击:', row.text, `@${row.x},${row.y}`);
    await sleep(/[.](png|jpe?g|svg|pdf)$/i.test(step) ? 2400 : 1200);
  }

  const before = await cdp.eval(MEASURE);
  console.log('注入后初始:', JSON.stringify(before));
  if (SHOT) await cdp.shot(SHOT + '-before.png');

  if (before.at) {
    await cdp.wheelAt(before.at.x, before.at.y, -300);
    await sleep(400);
    const zoomed = await cdp.eval(MEASURE);
    await cdp.drag(before.at.x, before.at.y, before.at.x - 110, before.at.y - 80);
    await sleep(300);
    const panned = await cdp.eval(MEASURE);
    console.log('滚轮缩放后:', JSON.stringify({ renderedPx: zoomed.renderedPx, zoomApplied: zoomed.zoomApplied, scroll: zoomed.scroll }));
    console.log('拖动平移后:', JSON.stringify({ scrollPos: panned.scrollPos, zoomApplied: panned.zoomApplied }));
    if (SHOT) await cdp.shot(SHOT + '-after.png');
  }
  cdp.close();
}
main().catch((e) => { console.error('失败:', e.message); process.exit(1); });
