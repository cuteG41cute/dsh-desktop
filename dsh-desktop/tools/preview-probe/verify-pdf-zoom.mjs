// PDF 缩放验证器（真实产品页面 / 真实桌面窗口）：
//   node e2e.mjs --edge [--inject 脚本]     无头 Edge 打开 3080（手动注入脚本，模拟桌面窗口）
//   node e2e.mjs --attach 9411              附着到真实桌面窗口（exe 已经把脚本注入进去了）
// 导航：右栏 → 工作区文件 → dsh-desktop/tools/preview-probe/fixtures/three-pages.pdf
import { spawn } from 'node:child_process'
import { readFileSync, mkdirSync, existsSync } from 'node:fs'
import { createHash, createHmac } from 'node:crypto'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

const args = process.argv.slice(2)
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d }
const MODE = args.includes('--attach') ? 'attach' : 'edge'
const PORT = Number(MODE === 'attach' ? opt('--attach', 9411) : opt('--port', 9344))
const INJECT = opt('--inject', '')
const STEPS = opt('--steps', 'dsh-desktop,tools,preview-probe,fixtures,three-pages.pdf').split(',').filter(Boolean)
const APPBASE = opt('--app', 'http://127.0.0.1:3080')
const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(existsSync)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const OBSERVE = args.includes('--observe')       // 只观察、不断言（用来记录旧版行为）
let pass = 0, fail = 0
const check = (label, cond, extra) => {
  if (OBSERVE) { console.log(cond ? '  · ' + label + ' → 成立' : '  · ' + label + ' → 不成立', extra === undefined ? '' : JSON.stringify(extra)); return }
  if (cond) { pass++; console.log('  \u2713', label) } else { fail++; console.log('  \u2717', label, extra === undefined ? '' : JSON.stringify(extra)) }
}

function mintCookie(authority) {
  const home = process.env.DSH_HOME || join(process.env.USERPROFILE, '.dsh')
  const raw = /client-connection\/browser-session:[\s\S]*?secret:\s*([A-Za-z0-9_-]+)/.exec(readFileSync(join(home, '.credentials.yaml'), 'utf8'))[1]
  const secret = Buffer.from(raw.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - raw.length % 4) % 4), 'base64')
  const b64 = (b) => Buffer.from(b).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  const name = 'dsh-auth-' + b64(createHash('sha256').update(authority).digest())
  const now = Date.now()
  const body = b64(Buffer.from(JSON.stringify({ version: 1, authority, issuedAt: now, expiresAt: now + 7 * 864e5 })))
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
  click(x, y, count = 1) {
    return this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: count, buttons: 1 })
      .then(() => this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: count, buttons: 0 }))
  }
  close() { try { this.ws.close() } catch { } }
}

const HELPERS = `window.__pvE2E = {
  /* 文件树的行有稳定的 data-files-entry / data-files-path；按路径逐级定位，
     并报告该目录是否已展开（已展开就不要再点，否则会把上一轮的状态收起来） */
  rowAt: function (step, parentPath) {
    var rows = [].slice.call(document.querySelectorAll('[data-files-entry][data-files-path]'));
    var norm = function (p) { return String(p || '').replace(/\\\\/g, '/'); };
    var base = function (p) { var n = norm(p); var a = n.lastIndexOf('/'); return a < 0 ? n : n.slice(a + 1); };
    var dirOf = function (p) { var n = norm(p); var a = n.lastIndexOf('/'); return a < 0 ? '' : n.slice(0, a); };
    var wantDir = norm(parentPath);
    var hit = null;
    for (var i = 0; i < rows.length; i++) {
      var p = rows[i].getAttribute('data-files-path') || '';
      if (base(p) !== step) continue;
      if (wantDir && dirOf(p) !== wantDir) continue;
      hit = rows[i]; break;
    }
    if (!hit) {
      return { err: 'not found', want: step, under: wantDir,
        sample: rows.filter(function (r) { return !wantDir || dirOf(r.getAttribute('data-files-path')) === wantDir; })
          .map(function (r) { return base(r.getAttribute('data-files-path')); }).slice(0, 24) };
    }
    var path = norm(hit.getAttribute('data-files-path'));
    var entry = hit.getAttribute('data-files-entry');
    hit.scrollIntoView({ block: 'center' });
    var r = hit.getBoundingClientRect();
    var expanded = rows.some(function (x) { return dirOf(x.getAttribute('data-files-path')) === path; });
    return { text: base(path), path: path, entry: entry, expanded: expanded,
      x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width) };
  },
  probe: function () {
    var vp = document.querySelector('[data-textpreview-body]');
    var pages = [].slice.call(document.querySelectorAll('[data-pdf-page]'));
    var canvases = [];
    for (var i = 0; i < pages.length; i++) { var c = pages[i].querySelector('canvas'); if (c) canvases.push(c); }
    var host = document.querySelector('[data-document-preview]');
    var badge = document.getElementById('dsh-pv-badge');
    var r = function (x) { return Math.round(x * 100) / 100; };
    var at = null;
    if (canvas0()) {
      var c0 = canvas0().getBoundingClientRect(), v0 = vp.getBoundingClientRect();
      at = {
        x: Math.round(Math.max(v0.left + 20, Math.min(c0.left + c0.width / 2, v0.right - 20))),
        y: Math.round(Math.max(v0.top + 20, Math.min(c0.top + 80, v0.bottom - 40)))
      };
    }
    function canvas0() { return canvases[0] || null; }
    return {
      url: location.href,
      bound: vp ? vp.classList.contains('dsh-pv-vp') : null,
      docId: host ? host.getAttribute('data-document-preview') : null,
      pages: pages.length,
      canvases: canvases.length,
      imgCount: document.querySelectorAll('[data-image-preview] img').length,
      naturalVar: canvases.map(function (c) { return c.style.getPropertyValue('--pdf-page-width') || ''; }),
      widths: canvases.map(function (c) { return r(c.getBoundingClientRect().width); }),
      inline: canvases.map(function (c) { return c.style.width || ''; }),
      inlineMax: canvases.map(function (c) { return c.style.maxWidth || ''; }),
      pageZoom: pages.map(function (p) { return p.style.zoom || ''; }),
      unclipped: document.querySelectorAll('[data-dsh-pv-overflow]').length,
      vp: vp ? { cw: vp.clientWidth, ch: vp.clientHeight, sw: vp.scrollWidth, sh: vp.scrollHeight, sl: Math.round(vp.scrollLeft), st: Math.round(vp.scrollTop) } : null,
      badge: badge ? badge.textContent : null,
      dpr: window.devicePixelRatio,
      vvScale: window.visualViewport ? Math.round(window.visualViewport.scale * 1000) / 1000 : null,
      at: at
    };
  },
  reset: function () { var vp = document.querySelector('[data-textpreview-body]'); if (vp) { vp.scrollTop = 0; vp.scrollLeft = 0; } return true; },
  pageDiag: function (i) {
    var p = document.querySelectorAll('[data-pdf-page]')[i];
    if (!p) return null;
    var c = p.querySelector('canvas');
    var r = p.getBoundingClientRect();
    return {
      rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      html: p.innerHTML.replace(/\s+/g, ' ').slice(0, 140),
      canvas: c ? { attrW: c.width, attrH: c.height, cssW: c.style.width || '', hidden: c.hasAttribute('hidden'), rendered: Math.round(c.getBoundingClientRect().width), varW: c.style.getPropertyValue('--pdf-page-width') || '' } : null
    };
  },
  showPage: function (i) { var p = document.querySelectorAll('[data-pdf-page]')[i]; if (!p) return false; p.scrollIntoView({ block: 'center' }); return true; },
  scrollEnd: function () { var vp = document.querySelector('[data-textpreview-body]'); vp.scrollLeft = vp.scrollWidth; vp.scrollTop = vp.scrollHeight; return { sl: vp.scrollLeft, st: vp.scrollTop, maxX: vp.scrollWidth - vp.clientWidth, maxY: vp.scrollHeight - vp.clientHeight }; },
  anchor: function (x, y) { var c = document.querySelector('[data-pdf-page] canvas'); if (!c) return null; var r = c.getBoundingClientRect(); return { u: (x - r.left) / r.width, v: (y - r.top) / r.height }; }
}; 'ok'`

async function main() {
  let edge = null, cdp = null
  if (MODE === 'edge') {
    const profile = join(tmpdir(), 'dsh-pve2e-' + Date.now())
    mkdirSync(profile, { recursive: true })
    edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
      '--window-size=1440,900', '--no-first-run', 'about:blank'], { stdio: 'ignore' })
  }
  try {
    let list = null
    for (let i = 0; i < 80; i++) { try { list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (list.some((t) => t.type === 'page')) break } catch { } await sleep(250) }
    if (!list) throw new Error('连不上 CDP 端口 ' + PORT)
    const page = list.find((t) => t.type === 'page' && /3080|DeepSeek|localhost/.test(t.url + t.title)) || list.find((t) => t.type === 'page')
    cdp = await Cdp.connect(page.webSocketDebuggerUrl)
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Network.enable')
    console.log('模式:', MODE, '| 页面:', page.title, '|', page.url)

    if (MODE === 'edge') {
      const ck = mintCookie('127.0.0.1:3080')
      await cdp.send('Network.setCookie', { name: ck.name, value: ck.value, domain: '127.0.0.1', path: '/', httpOnly: true })
      await cdp.send('Page.navigate', { url: APPBASE + '/' })
      await sleep(8000)
    } else {
      await sleep(500)
    }
    await cdp.eval(HELPERS)

    /* 展开右栏 + 打开「工作区文件」标签 */
    const opened = await cdp.eval(`(() => {
      const vis = (b) => { const s = getComputedStyle(b); const r = b.getBoundingClientRect(); return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 1 && r.height > 1; };
      const byLabel = (t) => [...document.querySelectorAll('button[aria-label]')].find(b => (b.getAttribute('aria-label') || '') === t);
      const openBtn = byLabel('打开右侧边栏');
      if (openBtn && vis(openBtn)) { openBtn.click(); return 'expanded-panel'; }
      return 'panel-already-open';
    })()`)
    console.log('  右栏:', opened)
    await sleep(1500)
    const tab = await cdp.eval(`(() => {
      const btn = [...document.querySelectorAll('button[aria-label]')].find(b => (b.getAttribute('aria-label') || '') === '收起右侧边栏');
      if (!btn) return 'no-panel-btn';
      let panel = btn; for (let i = 0; i < 4 && panel; i++) panel = panel.parentElement;
      const nt = [...panel.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || '') === '新标签页');
      if (!nt) return 'no-newtab';
      nt.click();
      return new Promise(res => setTimeout(() => {
        const e = [...panel.querySelectorAll('button')].find(b => (b.textContent || '').trim().startsWith('工作区文件'));
        if (!e) return res('no-entry');
        e.click(); res('opened-files');
      }, 800));
    })()`)
    console.log('  文件标签:', tab)
    await sleep(2200)

    /* 导航到 PDF（按路径逐级定位；已展开的目录不再点，避免把状态收起来） */
    let parent = await cdp.eval(`(() => { const r = document.querySelector('[data-files-root]'); if (!r) return ''; return (r.getAttribute('data-files-root') || '').replace(/\\\\/g, '/'); })()`)
    console.log('  文件树根:', parent)
    for (const step of STEPS) {
      const row = await cdp.eval(`window.__pvE2E.rowAt(${JSON.stringify(step)}, ${JSON.stringify(parent)})`)
      if (!row || row.err) { console.log('  ✗ 找不到', step, JSON.stringify(row)); break }
      const isFile = row.entry === 'file'
      if (!isFile && row.expanded) {
        console.log('  已展开:', row.text, row.path)
        parent = row.path
        continue
      }
      await cdp.click(row.x, row.y)
      console.log('  点击:', row.text, `@${row.x},${row.y}`, 'expanded =', row.expanded, '|', row.path)
      await sleep(isFile ? 3000 : 1300)
      if (!isFile) {
        const again = await cdp.eval(`window.__pvE2E.rowAt(${JSON.stringify(step)}, ${JSON.stringify(parent)})`)
        if (again && !again.err && !again.expanded) {   // 展开失败（点击被别的元素接住）→ 重试一次
          await cdp.click(again.x, again.y)
          console.log('  重新展开:', again.text)
          await sleep(1300)
        }
        parent = row.path
      }
    }

    if (INJECT) {
      const r = await cdp.eval(`(() => { try { ${readFileSync(INJECT, 'utf8')}; return 'injected'; } catch (e) { return 'ERR ' + e.message; } })()`)
      console.log('  注入脚本:', r)
      await sleep(1500)
    }
    await cdp.eval(HELPERS)

    /* 真实 DOM 长什么样 */
    const p0 = await cdp.eval('window.__pvE2E.probe()')
    console.log('\n真实 PDF 预览 DOM：')
    console.log('  pages =', p0.pages, ' canvases =', p0.canvases, ' [data-image-preview] img =', p0.imgCount)
    console.log('  --pdf-page-width =', JSON.stringify(p0.naturalVar))
    console.log('  canvas 宽 =', JSON.stringify(p0.widths), ' vp =', JSON.stringify(p0.vp))
    console.log('  bound =', p0.bound, ' unclipped =', p0.unclipped, ' docId =', p0.docId)
    check('真实页面：PDF 用的是 [data-pdf-page] > canvas 渲染器', p0.pages >= 1 && p0.canvases >= 1, { pages: p0.pages, canvases: p0.canvases })
    check('真实页面：产品在画布上写了 --pdf-page-width（已渲染的第一页）', parseFloat(p0.naturalVar[0]) > 40, p0.naturalVar)
    console.log('  已渲染页数 =', p0.widths.filter((w) => w > 0).length, '/', p0.canvases, '（后几页是滚动到位才渲染的）')
    check('真实页面：增强脚本已绑定预览视口', p0.bound === true, p0.bound)
    check('真实页面：初始未写内联宽度（保持产品响应式）', p0.inline.every((w) => w === ''), p0.inline)
    const renderedIdx = p0.widths.map((w, i) => (w > 0 ? i : -1)).filter((i) => i >= 0)
    const onlyRendered = (arr) => renderedIdx.map((i) => arr[i])

    const at = p0.at
    const wheel = async (dy, ctrl, ticks = 1) => {
      for (let i = 0; i < ticks; i++) {
        await cdp.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: at.x, y: at.y, deltaX: 0, deltaY: dy, modifiers: ctrl ? 2 : 0, pointerType: 'mouse' })
        await sleep(80)
      }
      await sleep(250)
    }

    /* 要求 3：单滚轮只滚动 */
    await cdp.eval('window.__pvE2E.reset()')
    const b3 = await cdp.eval('window.__pvE2E.probe()')
    await wheel(150, false, 3)
    const a3 = await cdp.eval('window.__pvE2E.probe()')
    console.log('\n要求3  单滚轮: scrollTop', b3.vp.st, '→', a3.vp.st, ' canvas 宽 =', JSON.stringify(a3.widths), ' 内联 =', JSON.stringify(a3.inline))
    check('要求3：单滚轮只上下滑动', a3.vp.st > b3.vp.st + 150, { before: b3.vp.st, after: a3.vp.st })
    check('要求3：单滚轮完全不缩放（没有任何内联宽度 / CSS zoom）',
      a3.inline.every((w) => w === '') && a3.pageZoom.every((z) => z === ''), { inline: a3.inline, zoom: a3.pageZoom })
    await cdp.eval('window.__pvE2E.reset()')

    /* 要求 1：Ctrl+滚轮全局缩放 */
    const b1 = await cdp.eval('window.__pvE2E.probe()')
    const an0 = await cdp.eval(`window.__pvE2E.anchor(${at.x}, ${at.y})`)
    await wheel(-120, true, 4)
    const a1 = await cdp.eval('window.__pvE2E.probe()')
    const an1 = await cdp.eval(`window.__pvE2E.anchor(${at.x}, ${at.y})`)
    console.log('要求1  Ctrl+滚轮×4: canvas 宽 =', JSON.stringify(a1.widths), ' badge =', a1.badge, ' 锚点', JSON.stringify([an0, an1]))
    const drawn1 = a1.widths.map((w, i) => (w > 0 ? i : -1)).filter((i) => i >= 0)
    check('要求1：已渲染的每一页都一起放大',
      drawn1.length >= 1 && drawn1.every((i) => a1.widths[i] > b1.widths[i] + 10), { before: b1.widths, after: a1.widths })
    check('要求1：各页倍率一致（同宽）', drawn1.every((i) => Math.abs(a1.widths[i] - a1.widths[drawn1[0]]) < 1.5), a1.widths)
    check('要求1：写的是绝对像素宽度（不是 CSS zoom）',
      drawn1.every((i) => /px$/.test(a1.inline[i])) && a1.pageZoom.every((z) => z === ''), a1.inline)
    check('要求1：以光标为锚（内容点几乎不动）', Math.abs(an0.u - an1.u) < 0.02 && Math.abs(an0.v - an1.v) < 0.02, { before: an0, after: an1 })

    /* 要求 2：可以放大到超出显示区域并且滚得动 */
    await wheel(-120, true, 14)
    const a2 = await cdp.eval('window.__pvE2E.probe()')
    const end = await cdp.eval('window.__pvE2E.scrollEnd()')
    console.log('要求2  继续放大: canvas 宽 =', JSON.stringify(a2.widths), ' vp =', JSON.stringify(a2.vp), ' badge =', a2.badge)
    console.log('        滚到最右下 =', JSON.stringify(end))
    check('要求2：画布宽超过视口宽', a2.widths[0] > a2.vp.cw, { canvas: a2.widths[0], vp: a2.vp.cw })
    check('要求2：横向可滚动', a2.vp.sw > a2.vp.cw + 50, a2.vp)
    check('要求2：确实滚得动', end.sl > 50 && end.st > 50, end)
    console.log('        WebView 页面缩放: dpr', p0.dpr, '→', a2.dpr, ' visualViewport.scale', p0.vvScale, '→', a2.vvScale)
    check('Ctrl+滚轮没有触发整个 WebView 的页面缩放（dpr / visualViewport.scale 未变）',
      a2.dpr === p0.dpr && a2.vvScale === p0.vvScale, { dpr: [p0.dpr, a2.dpr], scale: [p0.vvScale, a2.vvScale] })

    /* 延迟渲染的页：滚到底把它逼出来，必须按当前倍率补齐（真实产品里就是这个问题） */
    await cdp.eval('window.__pvE2E.showPage(2)')
    await sleep(3500)
    const late = await cdp.eval('window.__pvE2E.probe()')
    console.log('        滚到第 3 页后 canvas 宽 =', JSON.stringify(late.widths), ' 内联 =', JSON.stringify(late.inline))
    console.log('        第 3 页诊断 =', JSON.stringify(await cdp.eval('window.__pvE2E.pageDiag(2)')))
    const drawnLate = late.widths.map((w, i) => (w > 0 ? i : -1)).filter((i) => i >= 0)
    if (drawn1.length < p0.canvases) {
      check('延迟渲染的页渲染后自动按当前倍率补齐（与第一页同宽）',
        drawnLate.length > drawn1.length && drawnLate.every((i) => Math.abs(late.widths[i] - late.widths[drawnLate[0]]) < 2),
        { before: a2.widths, after: late.widths })
    } else {
      console.log('  （跳过延迟渲染检查：这次 3 页都已渲染，本轮窗口复用了上次的状态）')
    }

    /* 双击：任意倍率 → 适宽 → 100% */
    const dbl = async () => {
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: at.x, y: at.y, button: 'left', clickCount: 2, buttons: 1 })
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: at.x, y: at.y, button: 'left', clickCount: 2, buttons: 0 })
      await sleep(400)
    }
    await cdp.eval('window.__pvE2E.reset()')
    await dbl()
    const dfit = await cdp.eval('window.__pvE2E.probe()')
    await dbl()
    const d100 = await cdp.eval('window.__pvE2E.probe()')
    console.log('双击 → 适宽 canvas 宽 =', JSON.stringify(dfit.widths), ' badge =', dfit.badge)
    console.log('再双击 → 100% canvas 宽 =', JSON.stringify(d100.widths), ' badge =', d100.badge)
    check('双击切到「适宽」（= 产品自己的适宽宽度）', Math.abs(dfit.widths[0] - p0.widths[0]) < 3, { fit: dfit.widths[0], product: p0.widths[0] })
    check('再双击切到 100%（= --pdf-page-width）', Math.abs(d100.widths[0] - parseFloat(p0.naturalVar[0])) < 3, { at100: d100.widths[0], natural: p0.naturalVar[0] })

    const errs = cdp.events.filter((e) => e.method === 'Runtime.exceptionThrown')
    console.log('\n未捕获异常 =', errs.length)
    check('零未捕获异常', errs.length === 0, errs.slice(0, 2).map((e) => e.params.exceptionDetails.text))
  } finally {
    if (edge) { try { edge.kill() } catch { } }
    if (cdp) cdp.close()
  }
  console.log('\n结果: 通过 ' + pass + ' / 失败 ' + fail)
  process.exit(fail ? 1 : 0)
}
main().catch((e) => { console.error('E2E 出错:', e.message); process.exit(2) })
