// 把设计稿里关键元素的几何与配色导出成 JSON —— GTK 复刻的"施工图"。
//
// 用法（仓库根）：
//   node dsh-desktop/linux/manager/tools/design-spec.mjs frost day dashboard
//   输出 dsh-desktop/linux/manager/design/references/spec-<theme>-<mode>-<page>.json
//
// 每个元素给出：x/y/w/h（相对 .app-shell）、外边距、内边距、圆角、边框、背景、颜色、
// 字体大小/字重/行高、以及要不要 overflow。GTK 侧只要把这些数字对上，几何就一致了。
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const MANAGER = join(HERE, '..');
const DESIGN = join(MANAGER, 'design', 'index.html');
const OUT = join(MANAGER, 'design', 'references');
const SIZE = (process.env.DSH_DESIGN_SIZE || '1440x900').split('x').map(Number);
const theme = process.argv[2] || 'frost';
const mode = process.argv[3] || 'day';
const page = process.argv[4] || 'dashboard';

const CANDIDATES = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome',
];
const BROWSER = process.env.DSH_RENDER_BROWSER || CANDIDATES.find(existsSync);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 设计稿里要量尺寸的元素（顺序即结构顺序）
const SELECTORS = [
  ['.app-shell', 'shell'],
  ['.sidebar', 'sidebar'],
  ['.brand', 'brand'],
  ['.brand-mark', 'brand-mark'],
  ['.side-section-title', 'side-title'],
  ['.instance-list', 'instance-list'],
  ['.instance-item', 'instance-item'],
  ['.instance-item.active', 'instance-item-active'],
  ['.instance-avatar', 'avatar'],
  ['.new-instance', 'new-instance'],
  ['.sidebar-bottom', 'sidebar-bottom'],
  ['.side-caption', 'side-caption'],
  ['.side-link', 'side-link'],
  ['.runtime', 'runtime'],
  ['.main-panel', 'main'],
  ['.topbar', 'topbar'],
  ['.breadcrumb', 'breadcrumb'],
  ['.top-actions', 'top-actions'],
  ['.theme-trigger', 'theme-trigger'],
  ['.mode-toggle', 'mode-toggle'],
  ['.content', 'content'],
  ['.page-heading', 'page-heading'],
  ['.eyebrow', 'eyebrow'],
  ['.title-line h1', 'h1'],
  ['.status-badge', 'status-badge'],
  ['.btn-primary', 'btn-primary'],
  ['.overview-grid', 'overview-grid'],
  ['.instance-card', 'instance-card'],
  ['.control-card', 'control-card'],
  ['.card', 'card'],
  ['.card-label', 'card-label'],
  ['.subtle-tag', 'subtle-tag'],
  ['.large-avatar', 'large-avatar'],
  ['.metric-row', 'metric-row'],
  ['.quick-section', 'quick-section'],
  ['.section-heading', 'section-heading'],
  ['.quick-grid', 'quick-grid'],
  ['.quick-action', 'quick-action'],
  ['.quick-icon', 'quick-icon'],
  ['.log-card', 'log-card'],
  ['.log-header', 'log-header'],
  ['.log-line', 'log-line'],
  ['.page-footer', 'page-footer'],
  ['.settings-layout', 'settings-layout'],
  ['.settings-card', 'settings-card'],
];

const PROPS = [
  'marginTop', 'marginRight', 'marginBottom', 'marginLeft',
  'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomLeftRadius', 'borderBottomRightRadius',
  'borderTopWidth', 'borderTopColor', 'gap', 'rowGap', 'columnGap',
  'backgroundColor', 'backgroundImage', 'color', 'fontSize', 'fontWeight', 'lineHeight',
  'fontFamily', 'letterSpacing', 'boxShadow', 'display', 'flexDirection', 'justifyContent',
  'alignItems', 'overflow', 'opacity', 'borderStyle',
];

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
  const profile = join(tmpdir(), 'dsh-spec-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const proc = spawn(BROWSER, [
    '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
    '--no-first-run', '--hide-scrollbars', '--force-device-scale-factor=1',
    '--font-render-hinting=none', '--allow-file-access-from-files', 'about:blank',
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
    const pageTarget = (targets || []).find((t) => t.type === 'page');
    if (!pageTarget) throw new Error('no page target');
    const cdp = await Cdp.connect(pageTarget.webSocketDebuggerUrl);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride',
      { width: SIZE[0], height: SIZE[1], deviceScaleFactor: 1, mobile: false });
    await cdp.send('Page.navigate', { url: pathToFileURL(DESIGN).href });
    await sleep(1500);

    const data = await cdp.eval(`(() => {
      document.body.dataset.theme = ${JSON.stringify(theme)};
      document.body.dataset.mode = ${JSON.stringify(mode)};
      const dash = document.getElementById('dashboardPage');
      const set = document.getElementById('settingsPage');
      const bc = document.getElementById('breadcrumbCurrent');
      if (${JSON.stringify(page)} === 'settings') { dash.hidden = true; set.hidden = false; if (bc) bc.textContent = '管理器设置'; }
      else { dash.hidden = false; set.hidden = true; if (bc) bc.textContent = '实例概览'; }
      const shell = document.querySelector('.app-shell').getBoundingClientRect();
      const selectors = ${JSON.stringify(SELECTORS)};
      const props = ${JSON.stringify(PROPS)};
      const out = [];
      for (const [sel, name] of selectors) {
        const el = document.querySelector(sel);
        if (!el) { out.push({ name, selector: sel, missing: true }); continue; }
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        const style = {};
        for (const p of props) style[p] = cs[p];
        out.push({
          name, selector: sel,
          rect: {
            x: +(r.x - shell.x).toFixed(2), y: +(r.y - shell.y).toFixed(2),
            w: +r.width.toFixed(2), h: +r.height.toFixed(2),
          },
          style,
        });
      }
      return {
        theme: ${JSON.stringify(theme)}, mode: ${JSON.stringify(mode)}, page: ${JSON.stringify(page)},
        viewport: { w: ${SIZE[0]}, h: ${SIZE[1]} },
        shell: { x: shell.x, y: shell.y, w: +shell.width.toFixed(2), h: +shell.height.toFixed(2) },
        bodyFont: getComputedStyle(document.body).fontFamily,
        baseFontSize: getComputedStyle(document.body).fontSize,
        elements: out,
      };
    })()`);

    const file = join(OUT, `spec-${theme}-${mode}-${page}.json`);
    writeFileSync(file, JSON.stringify(data, null, 2));
    console.log('wrote ' + file);
    for (const e of (data.elements || []).slice(0, 60)) {
      if (e.missing) { console.log(`  ${e.name.padEnd(22)} MISSING ${e.selector}`); continue; }
      const r = e.rect;
      console.log(`  ${e.name.padEnd(22)} x=${String(r.x).padStart(6)} y=${String(r.y).padStart(6)} ` +
                  `w=${String(r.w).padStart(6)} h=${String(r.h).padStart(5)} ` +
                  `pad=${e.style.paddingTop}/${e.style.paddingRight} radius=${e.style.borderTopLeftRadius} ` +
                  `bg=${e.style.backgroundColor}`);
    }
  } finally {
    try { proc.kill(); } catch { /* gone */ }
  }
}

main().catch((e) => { console.error('FAIL: ' + (e && e.stack ? e.stack : e)); process.exit(1); });
