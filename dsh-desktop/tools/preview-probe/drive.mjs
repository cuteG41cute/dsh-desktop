// 预览驱动器：CDP 真实鼠标事件 —— 打开工作区文件 → 展开目录 → 点开图片 → 量尺寸 → 测滚轮/拖拽
// 用法：node drive.mjs [--apply <注入脚本>] [--shot <前缀>]
import { spawn } from 'node:child_process';
import { readFileSync, mkdirSync, rmSync, existsSync, writeFileSync } from 'node:fs';
import { createHash, createHmac } from 'node:crypto';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const INJECT = opt('--apply', '');
const SHOT = opt('--shot', join(tmpdir(), 'dsh-drive'));
const PORT = Number(opt('--port', 9336));
const TARGET_IMG = opt('--img', 'icon-source.png');
const STEPS = opt('--steps', '').split(',').filter(Boolean);
const EVALFILE = opt('--eval', '');

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
  async wheelAt(x, y, deltaY, deltaX = 0) {
    await this.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x, y, deltaX, deltaY, pointerType: 'mouse' });
  }
  async drag(x1, y1, x2, y2) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: x1, y: y1, button: 'left', clickCount: 1, buttons: 1 });
    const steps = 6;
    for (let i = 1; i <= steps; i++) {
      await this.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x1 + (x2 - x1) * i / steps, y: y1 + (y2 - y1) * i / steps, button: 'left', buttons: 1 });
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
  if (!panel) return { err: 'no panel' };
  return [...panel.querySelectorAll('li, [role="treeitem"], [role="option"]')].map(el => {
    const r = el.getBoundingClientRect();
    return { text: (el.textContent || '').trim().slice(0, 40), x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width) };
  }).filter(r => r.text && r.w > 40);
})()`;

const MEASURE_JS = `(() => {
  const cs = (el) => getComputedStyle(el);
  const info = (el) => ({ tag: el.tagName.toLowerCase(), cls: (el.className || '').toString().slice(0, 40),
    box: el.clientWidth + 'x' + el.clientHeight, scroll: el.scrollWidth + 'x' + el.scrollHeight,
    ov: cs(el).overflowX + '/' + cs(el).overflowY, bar: (el.offsetWidth - el.clientWidth) + 'x' + (el.offsetHeight - el.clientHeight), st: el.scrollTop, sl: el.scrollLeft });
  const imgs = [...document.querySelectorAll('img')].filter(i => i.naturalWidth >= 120);
  if (!imgs.length) return { imgs: 0 };
  const img = imgs[imgs.length - 1];
  const r = img.getBoundingClientRect();
  const chain = []; let el = img;
  while (el && el !== document.body) { chain.push(info(el)); el = el.parentElement; }
  let sp = img.parentElement, g = 0;
  while (sp && g++ < 12) { const c = cs(sp); if (/(auto|scroll)/.test(c.overflowX + c.overflowY)) break; sp = sp.parentElement; }
  return { imgs: imgs.length, natural: img.naturalWidth + 'x' + img.naturalHeight,
    rendered: Math.round(r.width) + 'x' + Math.round(r.height),
    center: (() => {
      // 光标必须落在滚动视口内部（否则事件打不到目标）
      const vr = sp ? sp.getBoundingClientRect() : { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
      const x = Math.max(vr.left + 30, Math.min(r.left + Math.min(r.width / 2, 150), vr.right - 30));
      const y = Math.max(vr.top + 30, Math.min(r.top + Math.min(r.height / 2, 150), vr.bottom - 30));
      return { x: Math.round(x), y: Math.round(y) };
    })(),
    imgBox: { l: Math.round(r.left), t: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
    chain: chain.slice(0, 7),
    scrollport: sp ? { ...info(sp), zoom: cs(sp).zoom, w: sp.clientWidth, h: sp.clientHeight } : null };
})()`;

async function main() {
  const profile = join(tmpdir(), 'dsh-drive-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--window-size=1440,900', '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
  const log = [];
  try {
    let list = null;
    for (let i = 0; i < 40; i++) { try { list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (list.some((t) => t.type === 'page')) break; } catch {} await sleep(250); }
    const cdp = await Cdp.connect(list.find((t) => t.type === 'page').webSocketDebuggerUrl);
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Network.enable');
    const ck = mintCookie();
    await cdp.send('Network.setCookie', { name: ck.name, value: ck.value, domain: '127.0.0.1', path: '/', httpOnly: true });
    await cdp.send('Page.navigate', { url: 'http://127.0.0.1:3080/' });
    await sleep(7000);

    // 1) 打开「工作区文件」标签（JS 点击即可）
    log.push({ openTab: await cdp.eval(`(() => {
      const btn = [...document.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '') === '收起右侧边栏');
      let panel = btn; for (let i = 0; i < 4 && panel; i++) panel = panel.parentElement;
      const nt = [...panel.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '') === '新标签页');
      if (!nt) return 'no newtab';
      nt.click();
      return new Promise(res => setTimeout(() => {
        const e = [...panel.querySelectorAll('button')].find(b => (b.textContent || '').trim().startsWith('工作区文件'));
        if (!e) return res('no entry');
        e.click(); res('opened');
      }, 800));
    })()`) });
    await sleep(2200);

    // 2) 逐级展开目录并点开目标文件（真实鼠标点击）
    const plan = STEPS.length ? STEPS : ['dsh-desktop', TARGET_IMG];
    for (const step of plan) {
      const rows = await cdp.eval(LIST_JS);
      const row = rows.find((r) => r.text === step) || rows.find((r) => r.text.includes(step));
      if (!row) { log.push({ step, found: false, sample: rows.map((r) => r.text).slice(0, 12) }); break; }
      await cdp.clickAt(row.x, row.y);
      log.push({ step, clicked: row.text, at: [row.x, row.y] });
      await sleep(/[.](png|jpe?g|webp|gif|svg|pdf)$/i.test(step) ? 2600 : 1400);
    }

    // 3) 量预览
    const before = await cdp.eval(MEASURE_JS);
    log.push({ measuredBefore: before });
    if (SHOT) await cdp.shot(SHOT + '-01-before.png');

    // 4) 交互测试（先把滚动复位，保证起点一致）
    await cdp.eval("(() => { const i=[...document.querySelectorAll('img')].filter(x=>x.naturalWidth>=120).pop(); if(!i)return; let s=i.parentElement,g=0; while(s&&g++<12){const c=getComputedStyle(s); if(/(auto|scroll)/.test(c.overflowX+c.overflowY))break; s=s.parentElement;} if(s){s.scrollTop=0;s.scrollLeft=0;} })()");
    await sleep(200);
    if (before.center) {
      const sc0 = await cdp.eval(`(() => { const i=[...document.querySelectorAll('img')].filter(x=>x.naturalWidth>=120).pop(); let s=i.parentElement,g=0; while(s&&g++<12){const c=getComputedStyle(s); if(/(auto|scroll)/.test(c.overflowX+c.overflowY))break; s=s.parentElement;} return s?{st:s.scrollTop,sl:s.scrollLeft,sh:s.scrollHeight,sw:s.scrollWidth,ch:s.clientHeight,cw:s.clientWidth}:null; })()`);
      await cdp.wheelAt(before.center.x, before.center.y, 300);
      await sleep(400);
      const afterWheel = await cdp.eval(`(() => { const i=[...document.querySelectorAll('img')].filter(x=>x.naturalWidth>=120).pop(); let s=i.parentElement,g=0; while(s&&g++<12){const c=getComputedStyle(s); if(/(auto|scroll)/.test(c.overflowX+c.overflowY))break; s=s.parentElement;} return s?{st:s.scrollTop,sl:s.scrollLeft}:null; })()`);
      await cdp.drag(before.center.x, before.center.y, before.center.x - 90, before.center.y - 70);
      await sleep(300);
      const afterDrag = await cdp.eval(`(() => { const i=[...document.querySelectorAll('img')].filter(x=>x.naturalWidth>=120).pop(); let s=i.parentElement,g=0; while(s&&g++<12){const c=getComputedStyle(s); if(/(auto|scroll)/.test(c.overflowX+c.overflowY))break; s=s.parentElement;} return s?{st:s.scrollTop,sl:s.scrollLeft}:null; })()`);
      log.push({ baseline: { sc0, afterWheel, afterDrag } });
    }

    // 5) 可选：注入补丁并复测
    if (INJECT) {
      log.push({ inject: await cdp.eval(`(() => { try { ${readFileSync(INJECT, 'utf8')}; return 'ok'; } catch (e) { return 'ERR ' + e.message; } })()`) });
      await sleep(1500);
      const after = await cdp.eval(MEASURE_JS);
      log.push({ measuredAfterInject: after });
      if (after.center) {
        const before2 = await cdp.eval(`(() => { const i=[...document.querySelectorAll('img')].filter(x=>x.naturalWidth>=120).pop(); const r=i.getBoundingClientRect(); let s=i.parentElement,g=0; while(s&&g++<12){const c=getComputedStyle(s); if(/(auto|scroll)/.test(c.overflowX+c.overflowY))break; s=s.parentElement;} return { w:Math.round(r.width), h:Math.round(r.height), st:s.scrollTop, sl:s.scrollLeft }; })()`);
        await cdp.wheelAt(after.center.x, after.center.y, -300);
        await sleep(400);
        const zoomed = await cdp.eval(`(() => { const i=[...document.querySelectorAll('img')].filter(x=>x.naturalWidth>=120).pop(); const r=i.getBoundingClientRect(); return { w:Math.round(r.width), h:Math.round(r.height) }; })()`);
        await cdp.drag(after.center.x, after.center.y, after.center.x - 100, after.center.y - 80);
        await sleep(300);
        const panned = await cdp.eval(`(() => { const i=[...document.querySelectorAll('img')].filter(x=>x.naturalWidth>=120).pop(); let s=i.parentElement,g=0; while(s&&g++<12){const c=getComputedStyle(s); if(/(auto|scroll)/.test(c.overflowX+c.overflowY))break; s=s.parentElement;} return { st:s.scrollTop, sl:s.scrollLeft, sw:s.scrollWidth, sh:s.scrollHeight }; })()`);
        log.push({ afterInject_interaction: { before2, zoomed, panned } });

        // 诊断：手动 zoom / 合成滚轮 / 异常捕获
        const diag = await cdp.eval(`(() => {
          const out = { errs: [] };
          window.addEventListener('error', (e) => out.errs.push(String(e.message)));
          const vp = document.querySelector('.dsh-pv-vp');
          const img = [...document.querySelectorAll('img')].filter(i => i.naturalWidth >= 120).pop();
          out.hasFlag = !!window.__dshPreviewTools;
          out.hasVp = !!vp;
          out.hasStyle = !!document.getElementById('dsh-pv-style');
          out.imgBefore = img ? Math.round(img.getBoundingClientRect().width) : null;
          const frame = img ? img.parentElement : null;
          out.frameCls = frame ? (frame.className || '').toString().slice(0, 24) : null;
          out.frameWBefore = frame ? Math.round(frame.getBoundingClientRect().width) : null;
          if (frame) frame.style.zoom = '1.5';
          out.frameZoomInline = frame ? frame.style.zoom : null;
          out.imgAfterManualZoom = img ? Math.round(img.getBoundingClientRect().width) : null;
          out.frameWAfter = frame ? Math.round(frame.getBoundingClientRect().width) : null;
          if (frame) frame.style.zoom = '';
          if (vp && img) {
            const r = img.getBoundingClientRect();
            const ev = new WheelEvent('wheel', { deltaY: -200, clientX: r.left + 40, clientY: r.top + 40, bubbles: true, cancelable: true });
            vp.dispatchEvent(ev);
            out.wheelPrevented = ev.defaultPrevented;
            out.frameZoomAfterWheel = frame ? frame.style.zoom : null;
            out.imgAfterWheel = img ? Math.round(img.getBoundingClientRect().width) : null;
            out.badgeText = (document.getElementById('dsh-pv-badge') || {}).textContent || null;
          }
          return out;
        })()`);
        log.push({ diag });
      }
      if (SHOT) await cdp.shot(SHOT + '-02-after.png');
    }
    if (EVALFILE) {
      const out = await cdp.eval(`(async () => { ${readFileSync(EVALFILE, 'utf8')} })()`);
      console.log('=== 自定义求值 ===');
      console.log(typeof out === 'string' ? out : JSON.stringify(out, null, 1));
    }
    console.log(JSON.stringify(log, null, 1));
    if (SHOT) console.log('截图:', SHOT + '-*.png');
    cdp.close();
  } finally { edge.kill(); await sleep(400); try { rmSync(profile, { recursive: true, force: true }); } catch {} }
}
main().catch((e) => { console.error('失败:', e.message); process.exit(1); });
