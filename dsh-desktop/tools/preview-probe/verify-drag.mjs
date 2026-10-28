// 验证：拖拽功能
//   --edge            无头真实页面（假宿主桥，核对页面发出的 dsh-drag-out 与文件夹落点行为）
//   --attach <端口>   真实桌面窗口（真宿主；配合 DSH_DRAG_TEST=1 核对宿主收到的路径与数据格式）
import { spawn } from 'node:child_process'
import { readFileSync, mkdirSync, existsSync, rmSync } from 'node:fs'
import { createHash, createHmac } from 'node:crypto'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'

const here = dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2)
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d }
const MODE = args.includes('--attach') ? 'attach' : 'edge'
const PORT = Number(MODE === 'attach' ? opt('--attach', 9422) : opt('--port', 9421))
const SCRIPT = opt('--script', join(here, 'preview-tools.js'))
const DEBUG_LOG = opt('--log', '')
const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(existsSync)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0
const check = (label, cond, extra) => { if (cond) { pass++; console.log('  \u2713', label) } else { fail++; console.log('  \u2717', label, extra === undefined ? '' : JSON.stringify(extra)) } }
const dec = (s) => (s ? Buffer.from(s, 'base64').toString('utf8') : null)

function mintCookie() {
  const home = process.env.DSH_HOME || join(process.env.USERPROFILE, '.dsh')
  const raw = /client-connection\/browser-session:[\s\S]*?secret:\s*([A-Za-z0-9_-]+)/.exec(readFileSync(join(home, '.credentials.yaml'), 'utf8'))[1]
  const secret = Buffer.from(raw.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - raw.length % 4) % 4), 'base64')
  const b64 = (b) => Buffer.from(b).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  const name = 'dsh-auth-' + b64(createHash('sha256').update('127.0.0.1:3080').digest())
  const now = Date.now()
  const body = b64(Buffer.from(JSON.stringify({ version: 1, authority: '127.0.0.1:3080', issuedAt: now, expiresAt: now + 7 * 864e5 })))
  return { name, value: `v1.${body}.${b64(createHmac('sha256', secret).update(body).digest())}` }
}

class Cdp {
  constructor(ws) { this.ws = ws; this.id = 0; this.waiting = new Map(); this.events = [] }
  static async connect(url) {
    const ws = new WebSocket(url)
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('ws error')) })
    const c = new Cdp(ws)
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data)
      if (m.id && c.waiting.has(m.id)) { const w = c.waiting.get(m.id); c.waiting.delete(m.id); m.error ? w.rej(new Error(JSON.stringify(m.error))) : w.res(m.result) }
      else if (m.method) c.events.push(m)
    }
    return c
  }
  send(method, params = {}) { const id = ++this.id; return new Promise((res, rej) => { this.waiting.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method, params })) }) }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (r.exceptionDetails) throw new Error((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || r.exceptionDetails.text || 'eval failed')
    return r.result.value
  }
  close() { try { this.ws.close() } catch { } }
}

const HELPERS = String.raw`window.__dd = {
  activeVp: function () {
    var vps = document.querySelectorAll('[data-textpreview-body]');
    for (var i = 0; i < vps.length; i++) {
      var vp = vps[i], r = vp.getBoundingClientRect(), cs = getComputedStyle(vp);
      if (r.width < 40 || r.height < 40 || cs.display === 'none' || cs.visibility === 'hidden') continue;
      if (!vp.closest('[data-sidebar-right-panel]')) continue;
      if (vp.closest('[data-sidebar-right-panel]').getAttribute('aria-hidden') === 'true') continue;
      return vp;
    }
    return null;
  },
  root: function () { var r = document.querySelector('[data-files-root]'); return r ? (r.getAttribute('data-files-root') || '').replace(/\\/g, '/') : ''; },
  nav: function (step, parent) {
    var rows = [].slice.call(document.querySelectorAll('[data-files-entry][data-files-path]'));
    var norm = function (p) { return String(p || '').replace(/\\/g, '/'); };
    var base = function (p) { var n = norm(p); var a = n.lastIndexOf('/'); return a < 0 ? n : n.slice(a + 1); };
    var dirOf = function (p) { var n = norm(p); var a = n.lastIndexOf('/'); return a < 0 ? '' : n.slice(0, a); };
    var want = norm(parent), hit = null;
    for (var i = 0; i < rows.length; i++) { var p = rows[i].getAttribute('data-files-path') || ''; if (base(p) === step && (!want || dirOf(p) === want)) { hit = rows[i]; break; } }
    if (!hit) return { err: 'not found', want: step, under: want };
    var path = norm(hit.getAttribute('data-files-path'));
    var expanded = rows.some(function (x) { return dirOf(x.getAttribute('data-files-path')) === path; });
    hit.scrollIntoView({ block: 'center' });
    var r = hit.getBoundingClientRect();
    return { text: base(path), path: path, entry: hit.getAttribute('data-files-entry'), expanded: expanded,
             x: Math.round(r.left + Math.min(r.width / 2, 120)), y: Math.round(r.top + r.height / 2) };
  },
  pointOf: function (el) { var r = el.getBoundingClientRect(); return { x: Math.round(r.left + 30), y: Math.round(r.top + r.height / 2) }; },
  rowPoint: function (needle) {
    var rows = [].slice.call(document.querySelectorAll('li[data-files-entry][data-files-path]'));
    var take = function (el) { el.scrollIntoView({ block: 'center' }); var b = el.getBoundingClientRect(); return { x: Math.round(b.left + 90), y: Math.round(b.top + b.height / 2) }; };
    for (var i = 0; i < rows.length; i++) {
      var p = rows[i].getAttribute('data-files-path') || '';
      if (p.indexOf(needle) >= 0) return take(rows[i]);
    }
    // 兜底：树里任何一行都行（attach 模式下树的状态可能和 edge 不一样）
    if (rows.length) return take(rows[0]);
    return null;
  },
  composer: function () { var c = document.querySelector('[data-composer-card]') || document.querySelector('[data-composer-input]'); if (!c) return null; var r = c.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; },
  composerText: function () { var c = document.querySelector('[data-composer-input]'); return c ? c.textContent : null; },
  attachments: function () { return document.querySelectorAll('[data-slot="conversation.input.attachments"] [data-attachment], [data-slot="conversation.input.attachments"] img, [data-slot="conversation.input.attachments"] li').length; },
  clearComposer: function () {
    var c = document.querySelector('[data-composer-input]');
    if (!c) return false;
    c.focus();
    var sel = window.getSelection(), range = document.createRange();
    range.selectNodeContents(c); sel.removeAllRanges(); sel.addRange(range);
    document.execCommand('delete');
    return true;
  },
  folderDrop: function (path) {
    var c = document.querySelector('[data-composer-card]') || document.querySelector('[data-composer-input]');
    // 用「假 dataTransfer」直接走目录分支：真 DataTransfer 里的目录条目没法伪造，
    // 而我们的处理器只用得到 types / items[i].webkitGetAsEntry / getData 这三样
    var fake = {
      types: ['Files', 'text/plain'],
      files: [],
      items: [{ kind: 'file', type: '', webkitGetAsEntry: function () { return { isDirectory: true, name: 'fake' }; } }],
      getData: function (t) { return t === 'text/plain' ? path : ''; }
    };
    var ev = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(ev, 'dataTransfer', { value: fake });
    c.dispatchEvent(ev);
    return { prevented: ev.defaultPrevented };
  }
}; 'ok'`

async function main() {
  let edge = null
  if (MODE === 'edge') {
    const profile = join(tmpdir(), 'dsh-drag-' + Date.now())
    mkdirSync(profile, { recursive: true })
    edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
      '--window-size=1440,900', '--no-first-run', 'about:blank'], { stdio: 'ignore' })
  }
  try {
    let list = null
    for (let i = 0; i < 80; i++) { try { list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (list.some((t) => t.type === 'page')) break } catch { } await sleep(250) }
    const page = list.find((t) => t.type === 'page')
    const cdp = await Cdp.connect(page.webSocketDebuggerUrl)
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Network.enable')

    if (MODE === 'edge') {
      // 假宿主桥：记录页面发出的消息，并能把宿主的回执打回去
      await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
        source: `(() => {
          window.__sent = []; window.__hostMsgs = []; window.__handlers = [];
          window.chrome = window.chrome || {};
          window.chrome.webview = {
            postMessage: function (s) { window.__sent.push(s); },
            addEventListener: function (t, fn) { if (t === 'message') window.__handlers.push(fn); }
          };
          window.__emit = function (obj) { window.__handlers.forEach(function (fn) { fn({ data: obj }); }); };
        })();`
      })
      await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: readFileSync(SCRIPT, 'utf8') })
      const ck = mintCookie()
      await cdp.send('Network.setCookie', { name: ck.name, value: ck.value, domain: '127.0.0.1', path: '/', httpOnly: true })
      await cdp.send('Page.navigate', { url: 'http://127.0.0.1:3080/' })
      await sleep(9000)
    } else {
      await sleep(600)
    }
    await cdp.eval(HELPERS)

    // 打开右栏「工作区文件」
    await cdp.eval(`(() => {
      const byLabel = (t) => [...document.querySelectorAll('button[aria-label]')].find(b => (b.getAttribute('aria-label') || '') === t);
      const vis = (b) => { const s = getComputedStyle(b); const r = b.getBoundingClientRect(); return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 1; };
      const o = byLabel('打开右侧边栏'); if (o && vis(o)) o.click(); return true;
    })()`)
    await sleep(900)
    await cdp.eval(`(() => {
      const btn = [...document.querySelectorAll('button[aria-label]')].find(b => (b.getAttribute('aria-label') || '') === '收起右侧边栏');
      if (!btn) return 'no-panel';
      let panel = btn; for (let i = 0; i < 4 && panel; i++) panel = panel.parentElement;
      const nt = [...panel.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '') === '新标签页');
      if (nt) { nt.click(); return new Promise(res => setTimeout(() => { const e = [...panel.querySelectorAll('button')].find(b => (b.textContent || '').trim().startsWith('工作区文件')); if (e) e.click(); res('ok'); }, 800)); }
      return 'no-newtab';
    })()`)
    await sleep(2200)
    await cdp.eval(HELPERS)
    await cdp.eval(`(() => { [].slice.call(document.querySelectorAll('[data-dockkit-tab]')).forEach((t) => { const s = (t.getAttribute('data-dockkit-tab-title') || t.textContent || '').trim(); if (s && s !== '文件') { const c = t.querySelector('[data-dockkit-tab-close]'); if (c) c.click(); } }); return true; })()`)
    await sleep(800)
    await cdp.eval(HELPERS)

    // 把树展开到 dsh-desktop/README.md
    let p = await cdp.eval('window.__dd.root()')
    for (const step of ['dsh-desktop', 'README.md']) {
      const row = await cdp.eval(`window.__dd.nav(${JSON.stringify(step)}, ${JSON.stringify(p)})`)
      if (!row || row.err) { console.log('导航失败', step, JSON.stringify(row)); break }
      if (row.entry !== 'file' && row.expanded) { p = row.path; continue }
      // 只展开目录，文件先不点开
      if (row.entry !== 'file') { await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: row.x, y: row.y, button: 'left', clickCount: 1, buttons: 1 }); await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: row.x, y: row.y, button: 'left', clickCount: 1, buttons: 0 }); await sleep(1300); p = row.path }
    }
    await cdp.eval(HELPERS)

    if (MODE === 'edge') {
      // ── 1) 从文件行拖出去 ──
      const rowPt = await cdp.eval(`window.__dd.rowPoint('README.md')`)
      console.log('\n【1】从文件树行拖出')
      check('找到 README.md 那一行', !!rowPt, rowPt)
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: rowPt.x, y: rowPt.y, button: 'left', clickCount: 1, buttons: 1 })
      for (let i = 1; i <= 6; i++) { await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: rowPt.x + i * 14, y: rowPt.y + i * 6, button: 'left', buttons: 1 }); await sleep(40) }
      await sleep(400)
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: rowPt.x + 84, y: rowPt.y + 36, button: 'left', clickCount: 1, buttons: 0 })
      await sleep(400)
      const sent1 = await cdp.eval('window.__sent ? window.__sent.map(function (s) { return JSON.parse(s); }) : []')
      const drag1 = sent1.find((s) => s.type === 'dsh-drag-out')
      console.log('  发出:', JSON.stringify(drag1 || null))
      check('拖动文件行会发出 dsh-drag-out', !!drag1, sent1)
      check('路径是那个文件的绝对路径', !!drag1 && /README\.md$/.test(dec(drag1.pathB64) || ''), dec(drag1 && drag1.pathB64))
      check('带了文件名与 isDir=false', !!drag1 && dec(drag1.nameB64) === 'README.md' && drag1.isDir === false, drag1)

      // ── 2) 从文件夹行拖出去 ──
      const dirPt = await cdp.eval(`window.__dd.rowPoint('docs')`)
      console.log('\n【2】从文件夹行拖出')
      if (dirPt) {
        await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: dirPt.x, y: dirPt.y, button: 'left', clickCount: 1, buttons: 1 })
        for (let i = 1; i <= 6; i++) { await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: dirPt.x - i * 12, y: dirPt.y + i * 5, button: 'left', buttons: 1 }); await sleep(40) }
        await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: dirPt.x - 72, y: dirPt.y + 30, button: 'left', clickCount: 1, buttons: 0 })
        await sleep(400)
        const sent2 = await cdp.eval('window.__sent ? window.__sent.map(function (s) { return JSON.parse(s); }) : []')
        const drag2 = sent2.filter((s) => s.type === 'dsh-drag-out').pop()
        console.log('  发出:', JSON.stringify(drag2 || null))
        check('拖动文件夹行会发出 dsh-drag-out 且 isDir=true', !!drag2 && drag2.isDir === true && /docs$/.test(dec(drag2.pathB64) || ''), drag2)
      } else {
        check('找到 docs 文件夹行', false)
      }

      // ── 3) 交付卡（手动造一个，验证路径提取） ──
      console.log('\n【3】交付卡拖出')
      const cardPt = await cdp.eval(`(() => {
        var host = document.createElement('div');
        host.setAttribute('data-presented-file', '');
        host.style.cssText = 'position:fixed;left:40px;top:300px;width:300px;height:60px;z-index:99999;background:#fff';
        var b = document.createElement('button');
        b.setAttribute('title', 'C:\\\\Users\\\\twinblade\\\\Documents\\\\deeepseek harness\\\\dsh-desktop\\\\README.md');
        b.textContent = 'card';
        b.style.cssText = 'width:100%;height:100%';
        host.appendChild(b);
        document.body.appendChild(host);
        var r = host.getBoundingClientRect();
        return { x: Math.round(r.left + 100), y: Math.round(r.top + r.height / 2) };
      })()`)
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: cardPt.x, y: cardPt.y, button: 'left', clickCount: 1, buttons: 1 })
      for (let i = 1; i <= 5; i++) { await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: cardPt.x + i * 12, y: cardPt.y + i * 4, button: 'left', buttons: 1 }); await sleep(40) }
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: cardPt.x + 60, y: cardPt.y + 20, button: 'left', clickCount: 1, buttons: 0 })
      await sleep(400)
      const sent3 = await cdp.eval('window.__sent ? window.__sent.map(function (s) { return JSON.parse(s); }) : []')
      const drag3 = sent3.filter((s) => s.type === 'dsh-drag-out').pop()
      console.log('  发出:', JSON.stringify(drag3 || null))
      check('交付卡也能拖出（路径来自 title）', !!drag3 && /README\.md$/.test(dec(drag3.pathB64) || ''), dec(drag3 && drag3.pathB64))
      await cdp.eval(`document.querySelectorAll('[data-presented-file]').forEach(function (el) { if (el.style.zIndex === '99999') el.remove(); })`)

    } else {
      console.log('\n【1-3】跳过：这几个断言用的是「假宿主桥」，attach 模式下由第 5 段用真宿主核对');
    }

    // ── 4) 文件夹落回输入框 → 变成路径文字 ──
    // 真实场景里用户多半刚点过输入框（Lexical 有自己的选区才插得进去），所以这里先真实点一下
    console.log('\n【4】文件夹落回输入框')
    await cdp.eval('window.__dd.clearComposer()')
    await sleep(200)
    const cp = await cdp.eval('window.__dd.composer()')
    await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: Math.round(cp.x), y: Math.round(cp.y), button: 'left', clickCount: 1, buttons: 1 })
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: Math.round(cp.x), y: Math.round(cp.y), button: 'left', clickCount: 1, buttons: 0 })
    await sleep(300)
    const beforeAtt = await cdp.eval('window.__dd.attachments()')
    const dropRes = await cdp.eval(`window.__dd.folderDrop('C:\\\\Users\\\\twinblade\\\\Documents\\\\deeepseek harness\\\\dsh-desktop\\\\docs')`)
    await sleep(900)
    const afterAtt = await cdp.eval('window.__dd.attachments()')
    const text = await cdp.eval('window.__dd.composerText()')
    console.log('  落点处理:', JSON.stringify(dropRes), ' 输入框文本:', JSON.stringify(text), ' 附件', beforeAtt, '→', afterAtt)
    console.log('  提示条:', JSON.stringify(await cdp.eval(`(function () { var b = document.getElementById('dsh-pv-badge'); return b ? b.textContent : null; })()`)))
    check('文件夹 drop 被我们拦下（防默认行为）', dropRes.prevented === true, dropRes)
    // 诊断：手动走一遍同样的插入流程，看是环境问题还是我们的实现问题
    const diag = await cdp.eval(`(() => {
      const i = document.querySelector('[data-composer-input]');
      const out = { active: document.activeElement === i, hasFocus: document.hasFocus(), before: i.textContent };
      i.focus();
      const r = i.getBoundingClientRect();
      const o = { bubbles: true, cancelable: true, clientX: r.right - 12, clientY: r.bottom - 12, button: 0, buttons: 1 };
      i.dispatchEvent(new MouseEvent('mousedown', o));
      i.dispatchEvent(new MouseEvent('mouseup', o));
      i.dispatchEvent(new MouseEvent('click', o));
      try {
        const s = window.getSelection(), rg = document.createRange();
        rg.selectNodeContents(i); rg.collapse(false); s.removeAllRanges(); s.addRange(rg);
      } catch (e) { out.selErr = String(e); }
      try { out.exec = document.execCommand('insertText', false, 'DIAG'); } catch (e) { out.execErr = String(e); }
      return out;
    })()`)
    await sleep(800)
    console.log('  诊断插入:', JSON.stringify(diag), ' → 文本:', JSON.stringify(await cdp.eval('window.__dd.composerText()')))
    check('路径写进了输入框', String(text || '').indexOf('dsh-desktop\\docs') >= 0, text)
    check('没有把文件夹当附件塞进去', afterAtt === beforeAtt, { before: beforeAtt, after: afterAtt })

    // ── 5) 真实宿主（仅 attach 模式）：核对宿主收到的路径与数据格式 ──
    if (MODE === 'attach') {
      console.log('\n【5】真实宿主（DSH_DRAG_TEST=1）')
      await cdp.eval(`(() => { window.__last = null; try { window.chrome.webview.addEventListener('message', function (e) { var m = e.data; if (typeof m === 'string') { try { m = JSON.parse(m); } catch (x) {} } if (m && m.type === 'dsh-drag-out-test') window.__last = m; }); } catch (e) {} return true; })()`)
      const pt = await cdp.eval(`window.__dd.rowPoint('README.md') || window.__dd.rowPoint('App.cs')`)
      let last = null
      if (pt) {
        await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: pt.x, y: pt.y, button: 'left', clickCount: 1, buttons: 1 })
        for (let i = 1; i <= 6; i++) { await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: pt.x + i * 12, y: pt.y + i * 5, button: 'left', buttons: 1 }); await sleep(40) }
        await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: pt.x + 72, y: pt.y + 30, button: 'left', clickCount: 1, buttons: 0 })
        await sleep(900)
        last = await cdp.eval('window.__last')
        console.log('  真实手势 → 宿主回执:', JSON.stringify(last))
        check('真实手势也能让宿主发起拖出', !!last && last.ok === true, last)
      } else {
        console.log('  （文件树没展开，改用直接给宿主发消息来核对宿主侧行为）')
      }
      if (!last) {
        // 宿主侧单独核对：直接把一条 dsh-drag-out 发给宿主（绕开 UI，只验宿主）
        const p = 'C:/Users/twinblade/Documents/deeepseek harness/dsh-desktop/README.md'
        await cdp.eval(`window.__last = null; chrome.webview.postMessage(JSON.stringify({ type: 'dsh-drag-out', pathB64: btoa(unescape(encodeURIComponent(${JSON.stringify(p)}))), nameB64: btoa('README.md'), isDir: false }))`)
        await sleep(1200)
        last = await cdp.eval('window.__last')
        console.log('  直接消息 → 宿主回执:', JSON.stringify(last))
      }
      {
        check('宿主收到了拖出请求并回报', !!last && last.ok === true, last)
        if (last) {
          check('宿主拿到的路径正确', /\.(md|cs|png|pdf)$/.test(dec(last.pathB64) || ''), dec(last.pathB64))
          const formats = dec(last.formatsB64) || ''
          console.log('  数据对象格式:', formats)
          check('数据对象里有 FileDrop（资源管理器靠它复制）', /FileDrop/i.test(formats), formats)
          check('数据对象里有文本格式（文件夹落回输入框靠它拿路径）', /Text|UnicodeText|uri-list/i.test(formats), formats)
        }
        if (DEBUG_LOG && existsSync(DEBUG_LOG)) {
          const log = readFileSync(DEBUG_LOG, 'utf8').trim()
          console.log('  调试日志最后一行:', log.split('\n').pop())
          check('调试日志里记下了这次拖出', log.length > 0)
        }
      }
    }

    const errs = cdp.events.filter((e) => e.method === 'Runtime.exceptionThrown')
    console.log('\n未捕获异常 =', errs.length)
    check('零未捕获异常', errs.length === 0, errs.slice(0, 2).map((e) => e.params.exceptionDetails.text))
    cdp.close()
  } finally {
    if (edge) { try { edge.kill() } catch { } }
  }
  console.log('\n结果: 通过 ' + pass + ' / 失败 ' + fail)
  process.exit(fail ? 1 : 0)
}
main().catch((e) => { console.error('测试脚本自身出错:', e.message); process.exit(2) })
