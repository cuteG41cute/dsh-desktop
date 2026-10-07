// 通用探针：无头 Edge + CDP，自动登录 127.0.0.1:3080，然后执行指定 JS 文件里的表达式并打印结果。
// 用法：node eval.mjs <脚本.js> [--wait 毫秒] [--shot 截图路径]
import { spawn } from 'node:child_process';
import { readFileSync, mkdirSync, rmSync, existsSync, writeFileSync } from 'node:fs';
import { createHash, createHmac } from 'node:crypto';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
const args = process.argv.slice(2);
const scriptPath = args[0];
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const WAIT = Number(opt('--wait', 6500));
const SHOT = opt('--shot', '');
const PORT = Number(opt('--port', 9335));
const APP = 'http://127.0.0.1:3080';

function mintCookie() {
  const home = process.env.DSH_HOME || join(process.env.USERPROFILE, '.dsh');
  const text = readFileSync(join(home, '.credentials.yaml'), 'utf8');
  const raw = /client-connection\/browser-session:[\s\S]*?secret:\s*([A-Za-z0-9_-]+)/.exec(text)[1];
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
  close() { try { this.ws.close(); } catch {} }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const profile = join(tmpdir(), 'dsh-probe-' + Date.now());
  mkdirSync(profile, { recursive: true });
  const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--window-size=1440,900', '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
  try {
    let list = null;
    for (let i = 0; i < 40; i++) { try { list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (list.some((t) => t.type === 'page')) break; } catch {} await sleep(250); }
    const cdp = await Cdp.connect(list.find((t) => t.type === 'page').webSocketDebuggerUrl);
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Network.enable');
    const ck = mintCookie();
    await cdp.send('Network.setCookie', { name: ck.name, value: ck.value, domain: '127.0.0.1', path: '/', httpOnly: true });
    await cdp.send('Page.navigate', { url: APP + '/' });
    await sleep(WAIT);
    const code = readFileSync(scriptPath, 'utf8');
    const out = await cdp.eval(`(async () => { ${code} })()`);
    console.log(typeof out === 'string' ? out : JSON.stringify(out, null, 1));
    if (SHOT) { await cdp.shot(SHOT); console.log('截图:', SHOT); }
    cdp.close();
  } finally { edge.kill(); await sleep(400); try { rmSync(profile, { recursive: true, force: true }); } catch {} }
}
main().catch((e) => { console.error('失败:', e.message); process.exit(1); });
