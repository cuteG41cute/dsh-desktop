// 把设计稿里每套主题/模式的 CSS 变量（--accent、--card、--text …）全部取出来，
// 和 dsh_manager/themes.json 里生成好的令牌逐项对比 —— 配色偏差用数字查，比像素快。
//
// 用法（仓库根）：
//   node dsh-desktop/linux/manager/tools/design-tokens.mjs
//   产物：dsh-desktop/linux/manager/design/references/tokens.json
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const MANAGER = join(HERE, '..');
const DESIGN = join(MANAGER, 'design', 'index.html');
const OUT = join(MANAGER, 'design', 'references', 'tokens.json');

const CANDIDATES = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome',
];
const BROWSER = process.env.DSH_RENDER_BROWSER || CANDIDATES.find(existsSync);
if (!BROWSER) {
  console.error('FAIL: 找不到 Chromium 内核浏览器');
  process.exit(1);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Cdp {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map(); }
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('ws fail')); });
    const cdp = new Cdp(ws);
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && cdp.pending.has(m.id)) {
        const p = cdp.pending.get(m.id);
        cdp.pending.delete(m.id);
        m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
      }
    };
    return cdp;
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval threw');
    return r.result.value;
  }
}

async function freePort() {
  return await new Promise((res, rej) => {
    const s = createServer();
    s.on('error', rej);
    s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => res(port)); });
  });
}

const THEMES = ['frost', 'liquid', 'crystal', 'flat', 'alpine', 'dawn', 'sea'];

async function main() {
  mkdirSync(dirname(OUT), { recursive: true });
  const port = await freePort();
  const profile = join(tmpdir(), 'dsh-tokens-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const proc = spawn(BROWSER, [
    '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
    '--no-first-run', '--allow-file-access-from-files', 'about:blank',
  ], { stdio: 'ignore' });
  try {
    let targets = null;
    for (let i = 0; i < 80; i++) {
      try {
        targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        if (targets.some((t) => t.type === 'page')) break;
      } catch { /* wait */ }
      await sleep(200);
    }
    const page = (targets || []).find((t) => t.type === 'page');
    if (!page) throw new Error('no page target');
    const cdp = await Cdp.connect(page.webSocketDebuggerUrl);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Page.navigate', { url: pathToFileURL(DESIGN).href });
    await sleep(1500);

    const data = await cdp.eval(`(() => {
      const themes = ${JSON.stringify(THEMES)};
      const out = {};
      const body = document.body;
      // 先收集所有 --xxx 变量名（含随主题变化的）
      const names = new Set();
      for (const t of themes) {
        body.dataset.theme = t;
        const cs = getComputedStyle(body);
        for (let i = 0; i < cs.length; i++) {
          const p = cs[i];
          if (p.startsWith('--')) names.add(p);
        }
      }
      for (const t of themes) {
        for (const m of ['day', 'night']) {
          body.dataset.theme = t;
          body.dataset.mode = m;
          const cs = getComputedStyle(body);
          const vals = {};
          for (const n of names) {
            const v = cs.getPropertyValue(n).trim();
            if (v) vals[n.slice(2)] = v;   // 去掉前导 --
          }
          out[t + '-' + m] = vals;
        }
      }
      body.dataset.theme = 'frost';
      body.dataset.mode = 'day';
      return { names: Array.from(names).map((n) => n.slice(2)).sort(), values: out };
    })()`);
    writeFileSync(OUT, JSON.stringify(data, null, 1));
    console.log(`wrote ${OUT}: ${data.names.length} tokens × ${Object.keys(data.values).length} combos`);
    console.log('tokens: ' + data.names.join(' '));
  } finally {
    try { proc.kill(); } catch { /* gone */ }
  }
}

main().catch((e) => { console.error('FAIL: ' + (e && e.stack ? e.stack : e)); process.exit(1); });
