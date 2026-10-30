// 把设计稿里的"背景层"逐主题/模式渲染成 PNG，给 GTK 当窗口背景用。
//
// 为什么这么做：GTK3 的 CSS 没有 backdrop-filter，也没有渐变以外的装饰能力；
// 与其在 GTK 里重画光斑/雪山/海浪（一定不像），不如直接用设计稿自己渲染出来。
// 页面里把 .app-shell 隐藏，剩下的就是 body 渐变 + .scene（光斑/山/浪/晨光/水晶）。
//
// 用法（仓库根目录）：node dsh-desktop/linux/manager/tools/render-backgrounds.mjs
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const MANAGER = join(HERE, '..');
const DESIGN = join(MANAGER, 'design', 'index.html');
const OUT = join(MANAGER, 'dsh_manager', 'backgrounds');
const THEMES = ['frost', 'liquid', 'crystal', 'flat', 'alpine', 'dawn', 'sea'];
const WIDTH = 1600;
const HEIGHT = 1000;

const CANDIDATES = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome',
];
const BROWSER = process.env.DSH_RENDER_BROWSER || CANDIDATES.find(existsSync);
if (!BROWSER) {
  console.error('FAIL: 找不到 Chromium 内核浏览器（可用 DSH_RENDER_BROWSER 指定）');
  process.exit(1);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Cdp {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map(); }
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('ws connect failed')); });
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
  async shot(path) {
    const r = await this.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    writeFileSync(path, Buffer.from(r.data, 'base64'));
  }
}

async function freePort() {
  return await new Promise((res, rej) => {
    const s = createServer();
    s.on('error', rej);
    s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => res(port)); });
  });
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const port = await freePort();
  const profile = join(tmpdir(), 'dsh-bg-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const proc = spawn(BROWSER, [
    '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
    '--no-first-run', '--hide-scrollbars', '--allow-file-access-from-files', 'about:blank',
  ], { stdio: 'ignore' });
  let done = 0;
  try {
    let targets = null;
    for (let i = 0; i < 80; i++) {
      try {
        targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        if (targets.some((t) => t.type === 'page')) break;
      } catch { /* not up */ }
      await sleep(200);
    }
    const page = (targets || []).find((t) => t.type === 'page');
    if (!page) throw new Error('浏览器没有暴露页面目标');
    const cdp = await Cdp.connect(page.webSocketDebuggerUrl);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride',
      { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
    await cdp.send('Page.navigate', { url: pathToFileURL(DESIGN).href });
    await sleep(1200);
    for (const theme of THEMES) {
      for (const mode of ['day', 'night']) {
        await cdp.eval(`(() => {
          document.body.dataset.theme = ${JSON.stringify(theme)};
          document.body.dataset.mode = ${JSON.stringify(mode)};
          const shell = document.querySelector('.app-shell');
          if (shell) shell.style.display = 'none';
          document.body.style.padding = '0';
          document.documentElement.style.overflow = 'hidden';
          return 1;
        })()`);
        await sleep(320);
        const file = join(OUT, `${theme}-${mode}.png`);
        await cdp.shot(file);
        done += 1;
        console.log('  ' + theme + ' / ' + mode + ' → ' + file);
      }
    }
  } finally {
    try { proc.kill(); } catch { /* gone */ }
  }
  console.log(`RESULT: ${done}/${THEMES.length * 2} 张背景已生成 → ${OUT}`);
  if (done !== THEMES.length * 2) process.exit(1);
}

main().catch((error) => {
  console.error('FAIL: ' + (error && error.stack ? error.stack : error));
  process.exit(1);
});
