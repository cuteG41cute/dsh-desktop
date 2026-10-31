// 把设计稿 design/index.html 渲染成参考图（GTK 复刻的比对基准）。
//
// 设计稿是 1440×900 的画布，.app-shell 就是"窗口"本身。这里按 viewport 渲染，
// 用 Page.captureScreenshot 的 clip 直接截 .app-shell 的盒子，得到与 GTK 窗口同尺寸的图。
//
// 用法（仓库根）：
//   node dsh-desktop/linux/manager/tools/design-shot.mjs                 # 全部主题/模式/页面
//   node dsh-desktop/linux/manager/tools/design-shot.mjs frost           # 只跑一套主题
//   DSH_DESIGN_SIZE=1440x900 node ... design-shot.mjs                     # 改画布尺寸
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const MANAGER = join(HERE, '..');
const DESIGN = join(MANAGER, 'design', 'index.html');
const OUT = join(HERE, '..', 'design', 'references');
const THEMES = ['frost', 'liquid', 'crystal', 'flat', 'alpine', 'dawn', 'sea'];
const PAGES = ['dashboard', 'settings'];
const SIZE = (process.env.DSH_DESIGN_SIZE || '1440x900').split('x').map(Number);
const WIDTH = SIZE[0];
const HEIGHT = SIZE[1];
const only = process.argv[2] ? [process.argv[2]] : THEMES;

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
  async shotClip(path, clip) {
    const r = await this.send('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: false, clip: { ...clip, scale: 1 },
    });
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
  const profile = join(tmpdir(), 'dsh-des-ref-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const proc = spawn(BROWSER, [
    '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
    '--no-first-run', '--hide-scrollbars', '--force-device-scale-factor=1',
    '--font-render-hinting=none', '--allow-file-access-from-files', 'about:blank',
  ], { stdio: 'ignore' });
  let done = 0;
  const total = only.length * 2 * PAGES.length;
  try {
    let targets = null;
    for (let i = 0; i < 80; i++) {
      try {
        targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        if (targets.some((t) => t.type === 'page')) break;
      } catch { /* not up yet */ }
      await sleep(200);
    }
    const page = (targets || []).find((t) => t.type === 'page');
    if (!page) throw new Error('浏览器没有暴露页面目标');
    const cdp = await Cdp.connect(page.webSocketDebuggerUrl);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    // viewport 用设计画布尺寸（1440×900）→ .app-shell 是 1392×852（四周 24px 留白），
    // 裁出来正好等于 GTK 窗口内容的尺寸。
    await cdp.send('Emulation.setDeviceMetricsOverride',
      { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
    await cdp.send('Page.navigate', { url: pathToFileURL(DESIGN).href });
    await sleep(1500);
    // 设计稿的字体栈是 Windows 专有的（Segoe UI / Microsoft YaHei UI），Linux 上没有。
    // 比对时把设计稿也换成 GTK 实际用的字体，diff 才只反映布局/配色误差。
    //   DSH_DESIGN_FONT='Noto Sans'    node design-shot.mjs
    if (process.env.DSH_DESIGN_FONT) {
      const font = process.env.DSH_DESIGN_FONT;
      const mono = process.env.DSH_DESIGN_MONO || '"DejaVu Sans Mono", monospace';
      await cdp.eval(`(() => {
        const st = document.createElement('style');
        st.textContent = 'body{--font:${font.replace(/'/g, "\\'")} !important}' +
          '.meta-main>span,.log-line,.info-list dd,.runtime small{font-family:${mono.replace(/'/g, "\\'")} !important}';
        document.head.appendChild(st);
        return 1;
      })()`);
      await sleep(300);
    }
    // 等字体就绪，否则第一张会和后面几张字重不一致
    await cdp.eval('document.fonts && document.fonts.ready ? document.fonts.ready.then(() => 1) : 1');

    for (const theme of only) {
      for (const mode of ['day', 'night']) {
        for (const pageName of PAGES) {
          const box = await cdp.eval(`(() => {
            document.body.dataset.theme = ${JSON.stringify(theme)};
            document.body.dataset.mode = ${JSON.stringify(mode)};
            const dash = document.getElementById('dashboardPage');
            const set = document.getElementById('settingsPage');
            const bc = document.getElementById('breadcrumbCurrent');
            if (${JSON.stringify(pageName)} === 'settings') { dash.hidden = true; set.hidden = false; if (bc) bc.textContent = '管理器设置'; }
            else { dash.hidden = false; set.hidden = true; if (bc) bc.textContent = '实例概览'; }
            const el = document.querySelector('.app-shell');
            const r = el.getBoundingClientRect();
            return { x: r.x, y: r.y, width: r.width, height: r.height,
                     font: getComputedStyle(document.body).fontFamily,
                     shell: [getComputedStyle(el).width, getComputedStyle(el).height] };
          })()`);
          await sleep(400);
          const file = join(OUT, `${theme}-${mode}-${pageName}.png`);
          await cdp.shotClip(file, { x: box.x, y: box.y, width: box.width, height: box.height });
          done += 1;
          console.log(`  ${theme}/${mode}/${pageName} → ${file}  shell=${box.shell.join('x')} font=${box.font}`);
        }
      }
    }
  } finally {
    try { proc.kill(); } catch { /* gone */ }
  }
  console.log(`RESULT: ${done}/${total} 参考图 → ${OUT}`);
  if (done !== total) process.exit(1);
}

main().catch((e) => {
  console.error('FAIL: ' + (e && e.stack ? e.stack : e));
  process.exit(1);
});
