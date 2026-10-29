// 实机录屏 v2：等界面真正就绪，注入一个 1px 动画强制持续重绘，
// 再用 Page.startScreencast 拿连续帧（否则 headless 只在画面变化时出帧）。
// 用法: node record2.mjs --out <帧目录> [--still <前缀>] [--session <标题片段>]
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createHash, createHmac } from 'node:crypto';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const OUT = opt('--out', join(tmpdir(), 'dsh-frames'));
const STILL = opt('--still', '');
const PORT = Number(opt('--port', '9351'));
const SESSION = opt('--session', 'dsh-api');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function mintCookie() {
  const home = process.env.DSH_HOME || join(process.env.USERPROFILE, '.dsh');
  const raw = /client-connection\/browser-session:[\s\S]*?secret:\s*([A-Za-z0-9_-]+)/
    .exec(readFileSync(join(home, '.credentials.yaml'), 'utf8'))[1];
  const secret = Buffer.from(raw.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - raw.length % 4) % 4), 'base64');
  const b64 = (b) => Buffer.from(b).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const name = 'dsh-auth-' + b64(createHash('sha256').update('127.0.0.1:3080').digest());
  const now = Date.now();
  const body = b64(Buffer.from(JSON.stringify({ version: 1, authority: '127.0.0.1:3080', issuedAt: now, expiresAt: now + 86400000 })));
  return { name, value: `v1.${body}.${b64(createHmac('sha256', secret).update(body).digest())}` };
}

class Cdp {
  constructor(ws) { this.ws = ws; this.id = 0; this.w = new Map(); this.onEvent = () => { }; }
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('ws')); });
    const c = new Cdp(ws);
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && c.w.has(m.id)) { const x = c.w.get(m.id); c.w.delete(m.id); m.error ? x.rej(new Error(JSON.stringify(m.error))) : x.res(m.result); }
      else if (m.method) c.onEvent(m.method, m.params);
    };
    return c;
  }
  send(m, p = {}) { const id = ++this.id; return new Promise((res, rej) => { this.w.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method: m, params: p })); }); }
  async eval(e) {
    const r = await this.send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval');
    return r.result.value;
  }
  async shot(p) { const r = await this.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(p, Buffer.from(r.data, 'base64')); }
  m(type, x, y, extra = {}) { return this.send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1, ...extra }); }
  async clickAt(x, y) { await this.m('mousePressed', x, y, { buttons: 1 }); await this.m('mouseReleased', x, y, { buttons: 0 }); }
  async rightClickAt(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'right', clickCount: 1, buttons: 2 });
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'right', clickCount: 1, buttons: 0 });
  }
  wheelAt(x, y, dY) { return this.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x, y, deltaX: 0, deltaY: dY, pointerType: 'mouse' }); }
  async drag(x1, y1, x2, y2, steps = 10) {
    await this.m('mousePressed', x1, y1, { buttons: 1 });
    for (let i = 1; i <= steps; i++) { await this.m('mouseMoved', x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps, { buttons: 1 }); await sleep(28); }
    await this.m('mouseReleased', x2, y2, { buttons: 0 });
  }
  async esc() {
    await this.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await this.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  }
}

const READY = `(() => ({
  rows: document.querySelectorAll('[role="treeitem"]').length,
  hasRight: [...document.querySelectorAll('button')].some(b => /右侧边栏/.test(b.getAttribute('aria-label') || '')),
  text: (document.body.innerText || '').slice(0, 80)
}))()`;

// 1px 动画：让画面每帧都有变化，screencast 才会连续出帧
const TICKER = `(() => {
  if (document.getElementById('rec-ticker')) return 'exists';
  const st = document.createElement('style');
  st.textContent = '@keyframes recTick{from{transform:translateX(0)}to{transform:translateX(2px)}}' +
    '#rec-ticker{position:fixed;right:0;bottom:0;width:2px;height:2px;opacity:.02;z-index:2147483647;' +
    'background:#000;pointer-events:none;animation:recTick .05s linear infinite alternate}';
  document.head.appendChild(st);
  const d = document.createElement('div');
  d.id = 'rec-ticker';
  document.body.appendChild(d);
  return 'injected';
})()`;

async function main() {
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  const profile = join(tmpdir(), 'dsh-rec2-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--window-size=1280,800', '--force-device-scale-factor=1', '--no-first-run', '--no-default-browser-check',
    'about:blank'], { stdio: 'ignore' });
  const marks = [];
  let n = 0, recording = false;
  try {
    let list = null;
    for (let i = 0; i < 60; i++) { try { list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (list.some(t => t.type === 'page')) break; } catch { } await sleep(250); }
    const cdp = await Cdp.connect(list.find(t => t.type === 'page').webSocketDebuggerUrl);
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Network.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
    // 桌面宿主会 AddScriptToExecuteOnDocumentCreated 注入预览增强；浏览器里没有，这里补上
    const previewJs = readFileSync(process.env.PREVIEW_JS
      || 'dsh-desktop/tools/preview-probe/preview-tools.js', 'utf8');
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: previewJs });
    marks.push({ injectedPreviewTools: previewJs.length });
    const ck = mintCookie();
    await cdp.send('Network.setCookie', { ...ck, domain: '127.0.0.1', path: '/', httpOnly: true });
    await cdp.send('Page.navigate', { url: 'http://127.0.0.1:3080/' });

    // 等界面真正就绪（工作区/会话列表加载完，之前 9s 太早，里面还是空状态）
    let ready = false;
    for (let i = 0; i < 60; i++) {
      await sleep(1000);
      const st = await cdp.eval(READY).catch(() => null);
      if (st && st.rows > 3 && st.hasRight) { ready = true; marks.push({ readyAfterSec: i + 1, rows: st.rows }); break; }
    }
    if (!ready) throw new Error('界面没就绪（还是空状态）');
    await sleep(1500);
    await cdp.eval(TICKER);

    // 先把目标会话点开
    const target = await cdp.eval(`(() => {
      const items = [...document.querySelectorAll('[role="treeitem"]')];
      const hit = items.find(el => (el.textContent || '').includes(${JSON.stringify(SESSION)})) || items[0];
      if (!hit) return null;
      const r = hit.getBoundingClientRect();
      return { x: Math.round(r.left + Math.min(80, r.width / 2)), y: Math.round(r.top + r.height / 2), text: (hit.textContent || '').trim().slice(0, 30) };
    })()`);
    if (target) { await cdp.clickAt(target.x, target.y); marks.push({ session: target.text }); }
    await sleep(2600);
    // 把鼠标挪开：否则侧栏的 hover 卡片会一直浮在输入框上方（视频里很难看）
    await cdp.m('mouseMoved', 980, 700, { buttons: 0 });
    await sleep(900);
    if (STILL) await cdp.shot(STILL + '-hero.png');

    cdp.onEvent = async (method, p) => {
      if (method !== 'Page.screencastFrame') return;
      if (recording) writeFileSync(join(OUT, `f${String(n++).padStart(5, '0')}.jpg`), Buffer.from(p.data, 'base64'));
      try { await cdp.send('Page.screencastFrameAck', { sessionId: p.sessionId }); } catch { }
    };
    const startRec = async () => {
      recording = true;
      await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 82, maxWidth: 1280, maxHeight: 800, everyNthFrame: 1 });
    };
    const stopRec = async () => { recording = false; try { await cdp.send('Page.stopScreencast'); } catch { } };
    const mark = (name) => marks.push({ name, frame: n });

    await startRec();
    mark('start');
    await sleep(1400);

    // 打开右侧栏
    mark('openRight');
    await cdp.eval(`(() => {
      const b = [...document.querySelectorAll('button')].find(x => {
        const l = x.getAttribute('aria-label') || '';
        return l.includes('右侧边栏') && !l.includes('收起');
      });
      if (b) b.click();
    })()`);
    await sleep(1600);

    // 文件标签
    mark('filesTab');
    await cdp.eval(`(() => {
      const shut = [...document.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '').includes('收起右侧边栏'));
      let panel = shut; for (let i = 0; i < 5 && panel; i++) panel = panel.parentElement;
      if (!panel) return;
      const nt = [...panel.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '') === '新标签页');
      if (nt) { nt.click(); return; }
      const t = [...panel.querySelectorAll('button')].find(b => (b.textContent || '').trim().startsWith('工作区文件'));
      if (t) t.click();
    })()`);
    await sleep(1100);
    await cdp.eval(`(() => {
      const shut = [...document.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '').includes('收起右侧边栏'));
      let panel = shut; for (let i = 0; i < 5 && panel; i++) panel = panel.parentElement;
      if (!panel) return;
      const e = [...panel.querySelectorAll('button')].find(b => (b.textContent || '').trim().startsWith('工作区文件'));
      if (e) e.click();
    })()`);
    await sleep(1900);
    if (STILL) await cdp.shot(STILL + '-files.png');

    // 展开目录 → 打开图片
    const ROWS = `(() => {
      const shut = [...document.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '').includes('收起右侧边栏'));
      let panel = shut; for (let i = 0; i < 5 && panel; i++) panel = panel.parentElement;
      if (!panel) return [];
      return [...panel.querySelectorAll('li, [role="treeitem"], [role="option"]')].map(el => {
        const r = el.getBoundingClientRect();
        return { text: (el.textContent || '').trim().slice(0, 40), x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width) };
      }).filter(r => r.text && r.w > 40);
    })()`;
    const steps = ['dsh-desktop', 'docs', 'banner.png'];
    for (const step of steps) {
      const rows = await cdp.eval(ROWS);
      const row = rows.find(r => r.text === step) || rows.find(r => r.text.includes(step));
      if (!row) { marks.push({ miss: step, sample: rows.map(r => r.text).slice(0, 10) }); break; }
      await cdp.clickAt(row.x, row.y);
      marks.push({ clicked: step });
      await sleep(/\.(png|jpe?g|webp|gif)$/i.test(step) ? 2600 : 1100);
    }
    if (STILL) await cdp.shot(STILL + '-preview.png');

    const pt = await cdp.eval(`(() => {
      const imgs = [...document.querySelectorAll('img')].filter(i => i.naturalWidth >= 120 && i.getBoundingClientRect().width > 40);
      if (!imgs.length) return null;
      const img = imgs[imgs.length - 1], r = img.getBoundingClientRect();
      let sp = img.parentElement, g = 0;
      while (sp && g++ < 12) { const c = getComputedStyle(sp); if (/(auto|scroll)/.test(c.overflowX + c.overflowY)) break; sp = sp.parentElement; }
      const vr = sp ? sp.getBoundingClientRect() : r;
      return {
        x: Math.round(Math.max(vr.left + 40, Math.min(r.left + Math.min(r.width / 2, 160), vr.right - 40))),
        y: Math.round(Math.max(vr.top + 40, Math.min(r.top + Math.min(r.height / 2, 160), vr.bottom - 40)))
      };
    })()`);

    if (pt) {
      mark('zoom');
      for (let i = 0; i < 3; i++) { await cdp.wheelAt(pt.x, pt.y, -200); await sleep(420); }
      await sleep(500);
      if (STILL) await cdp.shot(STILL + '-zoom.png');
      mark('pan');
      await cdp.drag(pt.x, pt.y, pt.x - 130, pt.y - 90);
      await sleep(700);
      mark('menu');
      await cdp.rightClickAt(pt.x - 100, pt.y - 70);
      await sleep(1800);
      if (STILL) await cdp.shot(STILL + '-menu.png');
      await cdp.esc();
      await sleep(900);
      mark('fit');
      for (let i = 0; i < 3; i++) { await cdp.wheelAt(pt.x, pt.y, 200); await sleep(380); }
    }
    await sleep(900);
    mark('end');
    await stopRec();
    writeFileSync(join(OUT, 'marks.json'), JSON.stringify({ frames: n, marks }, null, 2));
    console.log(JSON.stringify({ frames: n, marks }, null, 2));
  } finally { try { edge.kill(); } catch { } }
}
main().catch(e => { console.error('record failed:', e.message); process.exit(1); });
