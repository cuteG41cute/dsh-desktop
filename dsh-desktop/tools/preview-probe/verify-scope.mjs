// 作用范围验证器：用**真实鼠标/滚轮事件**（CDP Input，trusted events）核查
//   · 对话区：滚轮就是原生滚动（不被接管、滑动条仍是产品的 8px）
//   · 右栏图片：滚轮 = 缩放（被接管）
//   · 右栏文本 / 代码 / 日志：完全交还产品（不接管、原生滚动）
//   · 右栏 PDF：若渲染成 canvas/embed/img 则按图片处理
//   · 收起右侧栏：被接管元素归零、滚轮/拖动不再生效
//
// 用法（在本目录执行；会自动用 ~/.dsh/.credentials.yaml 签 3080 的会话 cookie）：
//   node verify-scope.mjs [--script preview-tools.js] [--port 9350] [--shot 前缀]
import { spawn } from 'node:child_process';
import { readFileSync, mkdirSync, rmSync, existsSync, writeFileSync } from 'node:fs';
import { createHash, createHmac } from 'node:crypto';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const SCRIPT = opt('--script', join(import.meta.dirname, 'preview-tools.js'));
const PORT = Number(opt('--port', 9350));
const SHOT = opt('--shot', '');
const SESSION = opt('--session', '手机远程对话dsh项目研究');

function mintCookie() {
  const home = process.env.DSH_HOME || join(process.env.USERPROFILE, '.dsh');
  const raw = /client-connection\/browser-session:[\s\S]*?secret:\s*([A-Za-z0-9_-]+)/.exec(readFileSync(join(home, '.credentials.yaml'), 'utf8'))[1];
  const secret = Buffer.from(raw.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - raw.length % 4) % 4), 'base64');
  const b64 = (b) => Buffer.from(b).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const authority = '127.0.0.1:3080';
  const name = 'dsh-auth-' + b64(createHash('sha256').update(authority).digest());
  const now = Date.now();
  const body = b64(Buffer.from(JSON.stringify({ version: 1, authority, issuedAt: now, expiresAt: now + 7 * 86400000 })));
  return { name, value: `v1.${body}.${b64(createHmac('sha256', secret).update(body).digest())}` };
}

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
      await sleep(40);
    }
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: x2, y: y2, button: 'left', clickCount: 1, buttons: 0 });
  }
  close() { try { this.ws.close(); } catch {} }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 右栏文件树 / 面板行（按坐标点）
const ROWS = `(() => {
  const p = document.querySelector('[data-sidebar-right-panel]');
  if (!p) return [];
  return [...p.querySelectorAll('[role="treeitem"], li, [role="option"]')].map(el => {
    const r = el.getBoundingClientRect();
    return { text: (el.textContent || '').trim().slice(0, 40), x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) };
  }).filter(r => r.text && r.w > 40 && r.h > 8);
})()`;

// 左栏工作区行（带 aria-expanded）
const WORKSPACES = `(() => {
  const t = document.querySelector('[role="tree"]');
  if (!t) return [];
  return [...t.querySelectorAll('[role="treeitem"], li')].filter(el => el.hasAttribute('aria-expanded')).map(el => {
    const r = el.getBoundingClientRect();
    return { text: (el.textContent || '').trim().slice(0, 40), x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) };
  }).filter(r => r.text && r.w > 40 && r.h > 8);
})()`;
const SESSIONS = `(() => {
  const t = document.querySelector('[role="tree"]');
  if (!t) return [];
  return [...t.querySelectorAll('[role="treeitem"], li')].filter(el => !el.hasAttribute('aria-expanded')).map(el => {
    const r = el.getBoundingClientRect();
    return { text: (el.textContent || '').trim().slice(0, 40), x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) };
  }).filter(r => r.text && r.w > 40 && r.h > 8);
})()`;

const CONV = `(() => {
  const c = document.querySelector('[data-conversation-scroll]');
  if (!c) return { none: true };
  const r = c.getBoundingClientRect();
  return { bound: c.classList.contains('dsh-pv-vp'), st: Math.round(c.scrollTop), sh: c.scrollHeight, ch: c.clientHeight,
    bar: c.offsetWidth - c.clientWidth, x: Math.round(r.left + r.width / 2), y: Math.round(r.top + 120) };
})()`;

const PREVIEW = `(() => {
  const vp = document.querySelector('[data-textpreview-body]');
  const host = vp ? vp.closest('[data-document-preview]') : null;
  const frame = vp ? vp.querySelector('[data-image-preview], [data-textpreview-plain], pre') : null;
  const media = vp ? vp.querySelector('img, canvas, embed, object, iframe, video') : null;
  const r = vp ? vp.getBoundingClientRect() : null;
  return {
    kind: host ? host.getAttribute('data-document-preview') : null,
    bound: document.querySelectorAll('.dsh-pv-vp').length,
    hasPre: vp ? !!vp.querySelector('pre, [data-textpreview-page], [data-textpreview-plain]') : null,
    media: media ? media.tagName.toLowerCase() : null,
    mediaW: media && media.tagName === 'IMG' ? media.naturalWidth : (media ? media.width : null),
    renderedW: media ? Math.round(media.getBoundingClientRect().width) : null,
    zoom: (media && media.parentElement) ? (media.parentElement.style.zoom || '(none)') : null,
    bar: vp ? (vp.offsetWidth - vp.clientWidth) : null,
    st: vp ? Math.round(vp.scrollTop) : null,
    sl: vp ? Math.round(vp.scrollLeft) : null,
    sh: vp ? vp.scrollHeight : null,
    ch: vp ? vp.clientHeight : null,
    center: r ? { x: Math.round(r.left + 140), y: Math.round(r.top + 140) } : null,
    panelOpen: (() => { const p = document.querySelector('[data-sidebar-right-panel]'); return p ? p.getAttribute('data-sidebar-right-open') : null; })(),
    zoomInline: [...document.querySelectorAll('[data-textpreview-body] *')].filter(e => e.style && e.style.zoom).length,
  };
})()`;

const TAB_TO_TREE = `(() => {
  const strip = document.querySelector('[data-dockkit-strip]');
  if (!strip) return { ok: false, why: 'no-strip' };
  const tabs = [...strip.querySelectorAll('[role="tab"]')];
  const t = tabs.find(x => /工作区文件|文件/.test((x.textContent || '').trim()));
  if (t) { t.click(); return { ok: true, how: 'existing' }; }
  const add = strip.querySelector('[data-dockkit-add-tab]');
  if (add) { add.click(); return { ok: true, how: 'menu' }; }
  return { ok: false, why: 'no-tab' };
})()`;

const PICK_TREE_ENTRY = `(() => {
  const cands = [...document.querySelectorAll('button, [role="menuitem"], [role="option"], li')];
  const e = cands.find(x => /工作区文件/.test((x.textContent || '').trim()));
  if (!e) return { ok: false, sample: cands.map(x => (x.textContent || '').trim()).filter(Boolean).slice(0, 20) };
  e.click(); return { ok: true };
})()`;

const TOGGLE = `(() => {
  const t = document.querySelector('[data-sidebar-right-toggle]');
  if (!t) return null;
  const r = t.getBoundingClientRect();
  return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), label: t.getAttribute('aria-label') };
})()`;

// 保证右栏正显示「工作区文件」标签（需要时走「新标签页」菜单）
async function ensureTreeTab(cdp, log, key) {  const a = await cdp.eval(TAB_TO_TREE);
  if (a && a.how === 'menu') {
    await sleep(900);
    const b = await cdp.eval(PICK_TREE_ENTRY);
    await sleep(1900);
    log.steps[key] = { ...a, entry: b };
    return;
  }
  await sleep(1600);
  log.steps[key] = a;
}

// 先把行滚进可见区再点（否则行在可视区外，坐标点击会漏掉）
const ROW_SCROLL = (name) => `(() => {
  const p = document.querySelector('[data-sidebar-right-panel]');
  if (!p) return false;
  const rows = [...p.querySelectorAll('[role="treeitem"], li, [role="option"]')];
  const n = ${JSON.stringify(name)};
  const el = rows.find(e => (e.textContent || '').trim() === n) || rows.find(e => (e.textContent || '').trim().startsWith(n));
  if (!el) return false;
  el.scrollIntoView({ block: 'center' });
  return true;
})()`;

// 展开目录行（已经是展开状态就别再点，否则会折叠）
const EXPANDED = (name) => `(() => {
  const p = document.querySelector('[data-sidebar-right-panel]');
  if (!p) return null;
  const rows = [...p.querySelectorAll('[role="treeitem"], li, [role="option"]')];
  const n = ${JSON.stringify(name)};
  const el = rows.find(e => (e.textContent || '').trim() === n) || rows.find(e => (e.textContent || '').trim().startsWith(n));
  return el ? el.getAttribute('aria-expanded') : null;
})()`;

// 文件树是虚拟列表（只渲染可见的少数行）：先回到顶部，再逐屏向下找目标行
const TREE_RESET = `(() => {
  const p = document.querySelector('[data-sidebar-right-panel]');
  if (!p) return false;
  const sc = [...p.querySelectorAll('*')].find(e => /(auto|scroll)/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 4);
  if (!sc) return false;
  sc.scrollTop = 0;
  return true;
})()`;
const TREE_PAGE = `(() => {
  const p = document.querySelector('[data-sidebar-right-panel]');
  if (!p) return false;
  const sc = [...p.querySelectorAll('*')].find(e => /(auto|scroll)/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 4);
  if (!sc) return false;
  sc.scrollTop += Math.max(80, Math.round(sc.clientHeight * 0.8));
  return { top: Math.round(sc.scrollTop), max: Math.round(sc.scrollHeight - sc.clientHeight) };
})()`;

async function findRowScrolled(cdp, name) {
  if (await cdp.eval(ROW_SCROLL(name))) return true;
  await cdp.eval(TREE_RESET);
  await sleep(300);
  for (let i = 0; i < 24; i++) {
    if (await cdp.eval(ROW_SCROLL(name))) return true;
    const p = await cdp.eval(TREE_PAGE);
    if (!p || (p.top >= p.max && i > 0)) return false;
    await sleep(280);
  }
  return false;
}

async function clickRow(cdp, name, wait) {
  const ok = await findRowScrolled(cdp, name);
  if (!ok) return { name, err: 'not-found' };
  await sleep(400);
  const r = (await cdp.eval(ROWS)).find((x) => x.text === name) || (await cdp.eval(ROWS)).find((x) => x.text.startsWith(name));
  if (!r) return { name, err: 'no-rect' };
  await cdp.clickAt(r.x, r.y);
  await sleep(wait || 2000);
  return { name, ok: true, at: [r.x, r.y] };
}

async function expandDir(cdp, name, wait) {
  const st = await cdp.eval(EXPANDED(name));
  if (st === null) { if (!(await findRowScrolled(cdp, name))) return { name, err: 'not-found' }; }
  else if (st === 'true') return { name, skipped: 'already-expanded' };
  return await clickRow(cdp, name, wait || 1300);
}

async function main() {
  const log = { script: SCRIPT, session: SESSION, steps: {} };
  const profile = join(tmpdir(), 'dsh-scope-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const edge = spawn(EDGE, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--headless=new',
    '--window-size=1440,900', '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
  try {
    let list = null;
    for (let i = 0; i < 40; i++) { try { list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (list.some((t) => t.type === 'page')) break; } catch {} await sleep(250); }
    const cdp = await Cdp.connect(list.find((t) => t.type === 'page').webSocketDebuggerUrl);
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Network.enable');
    // 与桌面壳一致：document-start 注入
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: readFileSync(SCRIPT, 'utf8') });
    const ck = mintCookie();
    await cdp.send('Network.setCookie', { name: ck.name, value: ck.value, domain: '127.0.0.1', path: '/', httpOnly: true });
    await cdp.send('Page.navigate', { url: 'http://127.0.0.1:3080/' });
    await sleep(8000);
    try {

    // 0) 先选中工作区「deeepseek harness」——右栏文件树的根目录跟着它走
    const wss = await cdp.eval(WORKSPACES);
    const ws = wss.find((r) => r.text.startsWith('deeepseek harness'));
    if (ws) { await cdp.clickAt(ws.x, ws.y); await sleep(2600); }
    log.steps.workspace = { clicked: ws ? ws.text : null, sample: wss.map((r) => r.text).slice(0, 12) };

    // 1) 打开一个真实会话（内容长、含代码块/图片），验证对话区不被接管
    const sess = await cdp.eval(SESSIONS);
    const row = sess.find((r) => r.text.startsWith(SESSION)) || sess.find((r) => r.text && !/新会话/.test(r.text));
    if (!row) { log.steps.session = { err: 'not-found', sample: sess.map((r) => r.text).slice(0, 12) }; }
    else {
      await cdp.clickAt(row.x, row.y); await sleep(5000);
      const viaClick = await cdp.eval(CONV);
      // 回到顶部再向下滚，方向才有意义
      await cdp.eval(`(() => { const c = document.querySelector('[data-conversation-scroll]'); if (c) c.scrollTop = 0; })()`);
      await sleep(400);
      const a = await cdp.eval(CONV);
      const TOP = `(() => { const c = document.querySelector('[data-conversation-scroll]'); const m = c && c.firstElementChild; return m ? Math.round(m.getBoundingClientRect().top) : null; })()`;
      const top0 = await cdp.eval(TOP);
      await cdp.wheelAt(a.x, a.y, 400); await sleep(700);
      const b = await cdp.eval(CONV);
      const top1 = await cdp.eval(TOP);
      log.steps.conversation = { clicked: row.text, before: a, after: b, contentTopBefore: top0, contentTopAfter: top1,
        scrolledDown: b.st - a.st, bound: b.bound, bar: b.bar, viaClick: { st: viaClick.st, sh: viaClick.sh } };
      if (SHOT) await cdp.shot(SHOT + '-conv.png');
    }

    // 2) 右栏文件标签 → 图片（应被接管：14px 滑动条 + 滚轮缩放 + 拖动平移）
    await ensureTreeTab(cdp, log, 'tabToTree');
    log.steps.treeRows = (await cdp.eval(ROWS)).slice(0, 8).map((r) => r.text);
    log.steps.clickDir = await expandDir(cdp, 'dsh-desktop');
    log.steps.clickDocs = await expandDir(cdp, 'docs');
    log.steps.clickImage = await clickRow(cdp, 'banner.png', 2800);
    {
      const p0 = await cdp.eval(PREVIEW);
      const pc = p0.center || { x: 900, y: 300 };
      await cdp.wheelAt(pc.x, pc.y, -300); await sleep(500);
      const p1 = await cdp.eval(PREVIEW);
      log.steps.image = { before: p0, after: p1, zoomed: p0.renderedW !== p1.renderedW, bound: p1.bound, at: pc };
      if (SHOT) await cdp.shot(SHOT + '-image.png');
      // 平移方向：先把滚动放到中间，再往右下拖 80/60 —— 内容应跟着指针走（同向）
      await cdp.eval(`(() => { const v = document.querySelector('[data-textpreview-body]'); if (v) { v.scrollTop = 100; v.scrollLeft = 100; } })()`);
      await sleep(300);
      const FRAME = `(() => { const v = document.querySelector('[data-textpreview-body]'); const f = v && (v.querySelector('[data-image-preview]') || v.querySelector('img')); const r = f ? f.getBoundingClientRect() : null; return r ? { l: Math.round(r.left), t: Math.round(r.top) } : null; })()`;
      const f0 = await cdp.eval(FRAME);
      await cdp.drag(pc.x, pc.y, pc.x + 80, pc.y + 60); await sleep(400);
      const f1 = await cdp.eval(FRAME);
      log.steps.imagePan = { frameBefore: f0, frameAfter: f1, contentDelta: f0 && f1 ? { dx: f1.l - f0.l, dy: f1.t - f0.t } : null, pointerDelta: { dx: 80, dy: 60 } };
    }

    // 3) 文本 / 代码 / 日志：必须完全交还产品（不加类、滚轮就是原生滚动）
    await ensureTreeTab(cdp, log, 'tabToTree2');
    log.steps.clickText = await clickRow(cdp, 'launcher.ps1', 2600);
    {
      const t0 = await cdp.eval(PREVIEW);
      const tc = t0.center || { x: 900, y: 300 };
      await cdp.wheelAt(tc.x, tc.y, 400); await sleep(700);
      const t1 = await cdp.eval(PREVIEW);
      log.steps.text = { before: t0, after: t1, scrolledDown: t1.st - t0.st, bound: t1.bound, bar: t1.bar, at: tc };
      if (SHOT) await cdp.shot(SHOT + '-text.png');
    }
    await ensureTreeTab(cdp, log, 'tabToTree2b');
    log.steps.clickLogs = await expandDir(cdp, 'logs');
    log.steps.clickLog = await clickRow(cdp, 'server.out.log', 2600);
    {
      const g0 = await cdp.eval(PREVIEW);
      const gc = g0.center || { x: 900, y: 300 };
      await cdp.wheelAt(gc.x, gc.y, 400); await sleep(700);
      const g1 = await cdp.eval(PREVIEW);
      log.steps.log = { before: g0, after: g1, scrolledDown: g1.st - g0.st, bound: g1.bound, bar: g1.bar };
    }

    // 4) PDF（应像图片一样被接管；渲染器用 canvas/embed/img 都算）
    await ensureTreeTab(cdp, log, 'tabToTree3');
    log.steps.clickPdfDir = await expandDir(cdp, 'docs');
    log.steps.clickPdf = await clickRow(cdp, '_probe-preview.pdf', 3400);
    {
      const d0 = await cdp.eval(PREVIEW);
      const dc = d0.center || { x: 900, y: 300 };
      await cdp.wheelAt(dc.x, dc.y, -300); await sleep(600);
      const d1 = await cdp.eval(PREVIEW);
      log.steps.pdf = { before: d0, after: d1, bound: d1.bound, zoom: d1.zoom, at: dc };
      if (SHOT) await cdp.shot(SHOT + '-pdf.png');
    }

    // 5) 收起右侧栏 → 一切失效
    const tg = await cdp.eval(TOGGLE);
    if (tg) {
      await cdp.clickAt(tg.x, tg.y); await sleep(1800);
      const c0 = await cdp.eval(PREVIEW);
      const conv = await cdp.eval(CONV);
      await cdp.wheelAt(c0.center ? c0.center.x : 900, c0.center ? c0.center.y : 300, -300); await sleep(400);
      await cdp.drag(conv.x || 600, conv.y || 200, (conv.x || 600) + 60, (conv.y || 200) + 40); await sleep(300);
      const c1 = await cdp.eval(PREVIEW);
      log.steps.closed = { toggle: tg, before: c0, after: c1, bound: c1.bound, zoomInline: c1.zoomInline, panelOpen: c1.panelOpen };
      if (SHOT) await cdp.shot(SHOT + '-closed.png');
      await cdp.clickAt(tg.x, tg.y); await sleep(1800);
      log.steps.reopened = await cdp.eval(PREVIEW);
    } else { log.steps.closed = { err: 'no toggle' }; }

    } catch (e) { log.error = String((e && e.message) || e); }
    cdp.close();
  } finally { edge.kill(); await sleep(400); try { rmSync(profile, { recursive: true, force: true }); } catch {} }
  console.log(JSON.stringify(log, null, 1));
}
main().catch((e) => { console.error('失败:', e.message); process.exit(1); });
