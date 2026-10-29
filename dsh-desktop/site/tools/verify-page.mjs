// 验收介绍页：全页截图（桌面 + 移动）、控制台错误、资源 404、字体回退
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';

const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
const TARGET = pathToFileURL(process.argv[2]).href;
const OUT = process.argv[3];
const PORT = 9355;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Cdp {
  constructor(ws) { this.ws = ws; this.id = 0; this.w = new Map(); this.events = []; }
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('ws')); });
    const c = new Cdp(ws);
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && c.w.has(m.id)) { const x = c.w.get(m.id); c.w.delete(m.id); m.error ? x.rej(new Error(JSON.stringify(m.error))) : x.res(m.result); }
      else if (m.method) c.events.push(m);
    };
    return c;
  }
  send(m, p = {}) { const id = ++this.id; return new Promise((res, rej) => { this.w.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method: m, params: p })); }); }
  async eval(e) {
    const r = await this.send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval');
    return r.result.value;
  }
  async shot(path, clip) {
    const r = await this.send('Page.captureScreenshot', clip
      ? { format: 'png', clip, captureBeyondViewport: true }
      : { format: 'png' });
    writeFileSync(path, Buffer.from(r.data, 'base64'));
  }
}

async function run(width, height, name, fullPage) {
  const profile = join(tmpdir(), 'page-check-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--no-first-run', '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' });
  try {
    let list = null;
    for (let i = 0; i < 60; i++) { try { list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (list.some(t => t.type === 'page')) break; } catch { } await sleep(250); }
    const cdp = await Cdp.connect(list.find(t => t.type === 'page').webSocketDebuggerUrl);
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
    await cdp.send('Network.enable'); await cdp.send('Log.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600 });
    await cdp.send('Page.navigate', { url: TARGET });
    await sleep(3500);
    // 截图前强制让所有入场元素可见（否则未滚动到的区块在整页截图里是透明的）
    await cdp.eval(`(() => { document.querySelectorAll('.reveal').forEach(el => el.classList.add('in')); document.documentElement.classList.remove('js'); return 1; })()`);
    await sleep(400);
    // 滚一遍触发 loading="lazy"，再回顶部截图
    await cdp.eval(`(async () => {
      const step = Math.round(window.innerHeight * 0.8);
      for (let y = 0; y <= document.documentElement.scrollHeight; y += step) {
        window.scrollTo(0, y);
        await new Promise(r => setTimeout(r, 120));
      }
      window.scrollTo(0, 0);
      await new Promise(r => setTimeout(r, 500));
      return 1;
    })()`);
    await sleep(600);
    const info = await cdp.eval(`(() => ({
      h: document.documentElement.scrollHeight,
      w: document.documentElement.clientWidth,
      fonts: getComputedStyle(document.body).fontFamily.slice(0, 60),
      videoReady: [...document.querySelectorAll('video')].map(v => ({ rs: v.readyState, dur: Math.round(v.duration * 10) / 10, err: v.error && v.error.code })),
      imgs: [...document.images].map(i => ({ src: i.currentSrc.split('/').pop(), ok: i.complete && i.naturalWidth > 0 })),
      overflow: [...document.querySelectorAll('*')].filter(el => el.scrollWidth > el.clientWidth + 3 && getComputedStyle(el).overflowX === 'visible').length
    }))()`);
    await cdp.shot(join(OUT, name + '-top.png'));
    if (fullPage) {
      await cdp.shot(join(OUT, name + '-full.png'), { x: 0, y: 0, width, height: info.h, scale: 1 });
    }
    const failed = cdp.events.filter(e => e.method === 'Network.loadingFailed').map(e => e.params.errorText);
    const consoleErrs = cdp.events.filter(e => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
      .map(e => (e.params.args || []).map(a => a.value || a.description || '').join(' '));
    const logErrs = cdp.events.filter(e => e.method === 'Log.entryAdded' && e.params.entry.level === 'error')
      .map(e => e.params.entry.text);
    return { ...info, failed, consoleErrs, logErrs };
  } finally { try { edge.kill(); } catch { } }
}

const OUTDIR = OUT;
mkdirSync(OUTDIR, { recursive: true });
const desktop = await run(1440, 900, 'desktop', true);
console.log('desktop:', JSON.stringify(desktop, null, 2));
await sleep(300);
const mobile = await run(390, 844, 'mobile', true);
console.log('mobile:', JSON.stringify({ h: mobile.h, w: mobile.w, failed: mobile.failed, consoleErrs: mobile.consoleErrs }, null, 2));
