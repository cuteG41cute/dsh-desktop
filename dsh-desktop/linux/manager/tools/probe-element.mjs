// 点探针：在指定主题/模式下，问浏览器"这个坐标最上面是谁画的、它什么背景"。
// 用来解释某个区域为什么会和 GTK 对不上（比如 crystal-night 里那块发白的面板）。
//
//   node tools/probe-element.mjs crystal night 600 300
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DESIGN = join(HERE, '..', 'design', 'index.html');
const theme = process.argv[2] || 'frost';
const mode = process.argv[3] || 'day';
const px = Number(process.argv[4] || 600);
const py = Number(process.argv[5] || 300);

const CANDIDATES = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
];
const BROWSER = process.env.DSH_RENDER_BROWSER || CANDIDATES.find(existsSync);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function freePort() {
  return await new Promise((res, rej) => {
    const s = createServer();
    s.on('error', rej);
    s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => res(port)); });
  });
}

async function main() {
  const port = await freePort();
  const profile = join(tmpdir(), 'dsh-probe-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const proc = spawn(BROWSER, ['--headless=new', `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`, '--no-first-run', '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' });
  try {
    let targets = null;
    for (let i = 0; i < 60; i++) {
      try {
        targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        if (targets.some((t) => t.type === 'page')) break;
      } catch { /* wait */ }
      await sleep(200);
    }
    const page = targets.find((t) => t.type === 'page');
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
    let id = 0;
    const pending = new Map();
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && pending.has(m.id)) {
        const p = pending.get(m.id);
        pending.delete(m.id);
        m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
      }
    };
    const send = (method, params = {}) => new Promise((res, rej) => {
      const i = ++id;
      pending.set(i, { res, rej });
      ws.send(JSON.stringify({ id: i, method, params }));
    });
    const evalJs = async (expr) => {
      const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval threw');
      return r.result.value;
    };
    await send('Page.enable');
    await send('Runtime.enable');
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    await send('Page.navigate', { url: pathToFileURL(DESIGN).href });
    await sleep(1200);
    const out = await evalJs(`(() => {
      document.body.dataset.theme = ${JSON.stringify(theme)};
      document.body.dataset.mode = ${JSON.stringify(mode)};
      const stack = document.elementsFromPoint(${px}, ${py});
      return stack.map((el) => {
        const cs = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return {
          tag: el.tagName.toLowerCase(),
          cls: el.className && el.className.toString().slice(0, 60),
          id: el.id || '',
          rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
          bg: cs.backgroundColor,
          bgImage: (cs.backgroundImage || '').slice(0, 80),
          opacity: cs.opacity,
          filter: cs.filter,
          backdrop: cs.backdropFilter,
          zIndex: cs.zIndex,
        };
      });
    })()`);
    console.log(JSON.stringify(out, null, 1));
  } finally {
    try { proc.kill(); } catch { /* gone */ }
  }
}

main().catch((e) => { console.error('FAIL: ' + e.message); process.exit(1); });
