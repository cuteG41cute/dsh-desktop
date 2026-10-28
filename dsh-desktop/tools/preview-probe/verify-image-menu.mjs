// 验证：右栏图片预览的右键菜单（真实产品页面 + 真实右键事件）
// 每个用例前整页重载，避免「多个预览标签同时存在」把探测指向非激活标签。
import { spawn } from 'node:child_process'
import { readFileSync, mkdirSync, existsSync } from 'node:fs'
import { createHash, createHmac } from 'node:crypto'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'

const here = dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2)
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d }
const PORT = Number(opt('--port', 9346))
const SCRIPT = opt('--script', join(here, 'preview-tools.js'))
const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
const ROOT = 'C:/Users/twinblade/Documents/deeepseek harness'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0
const check = (label, cond, extra) => { if (cond) { pass++; console.log('  \u2713', label) } else { fail++; console.log('  \u2717', label, extra === undefined ? '' : JSON.stringify(extra)) } }
const decB64 = (s) => (s ? Buffer.from(s, 'base64').toString('utf8') : null)

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
  async click(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1, buttons: 1 })
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1, buttons: 0 })
    await sleep(120)
  }
  async rightClick(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'right', clickCount: 1, buttons: 2 })
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'right', clickCount: 1, buttons: 0 })
    await sleep(350)
  }
  async key(key, code, vk, modifiers = 0) {
    await this.send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, windowsVirtualKeyCode: vk, modifiers })
    await this.send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: vk, modifiers })
    await sleep(200)
  }
  close() { try { this.ws.close() } catch { } }
}

/* 页面侧助手：所有探测都只看**激活并可见**的那个预览视口（与注入脚本的 liveViewport 同口径） */
const HELPERS = `window.__m = {
  activeVp: function () {
    var vps = document.querySelectorAll('[data-textpreview-body]');
    for (var i = 0; i < vps.length; i++) {
      var vp = vps[i], r = vp.getBoundingClientRect(), cs = getComputedStyle(vp);
      if (r.width < 40 || r.height < 40) continue;
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      if (!vp.closest('[data-sidebar-right-panel]')) continue;
      var panel = vp.closest('[data-sidebar-right-panel]');
      if (panel.getAttribute('aria-hidden') === 'true') continue;
      return vp;
    }
    return null;
  },
  nav: function (step, parent) {
    var rows = [].slice.call(document.querySelectorAll('[data-files-entry][data-files-path]'));
    var norm = function (p) { return String(p || '').replace(/\\\\/g, '/'); };
    var base = function (p) { var n = norm(p); var a = n.lastIndexOf('/'); return a < 0 ? n : n.slice(a + 1); };
    var dirOf = function (p) { var n = norm(p); var a = n.lastIndexOf('/'); return a < 0 ? '' : n.slice(0, a); };
    var want = norm(parent), hit = null;
    for (var i = 0; i < rows.length; i++) { var p = rows[i].getAttribute('data-files-path') || ''; if (base(p) === step && (!want || dirOf(p) === want)) { hit = rows[i]; break; } }
    if (!hit) return { err: 'not found', want: step, under: want };
    var path = norm(hit.getAttribute('data-files-path'));
    var expanded = rows.some(function (x) { return dirOf(x.getAttribute('data-files-path')) === path; });
    hit.scrollIntoView({ block: 'center' });
    var r = hit.getBoundingClientRect();
    return { text: base(path), path: path, entry: hit.getAttribute('data-files-entry'), expanded: expanded, x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
  },
  root: function () { var r = document.querySelector('[data-files-root]'); return r ? (r.getAttribute('data-files-root') || '').replace(/\\\\/g, '/') : ''; },
  menu: function () {
    var m = document.getElementById('dsh-pv-menu');
    if (!m) return null;
    var r = m.getBoundingClientRect();
    return {
      items: [].map.call(m.querySelectorAll('.dshm-mi'), function (b) { return b.textContent.trim(); }),
      disabled: [].map.call(m.querySelectorAll('.dshm-mi'), function (b) { return b.disabled; }),
      rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      inBody: m.parentElement === document.body
    };
  },
  itemPos: function (label) {
    var m = document.getElementById('dsh-pv-menu'); if (!m) return null;
    var b = [].filter.call(m.querySelectorAll('.dshm-mi'), function (x) { return x.textContent.indexOf(label) >= 0; })[0];
    if (!b) return null;
    var r = b.getBoundingClientRect();
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
  },
  imgPos: function () {
    var vp = window.__m.activeVp();
    var img = vp ? vp.querySelector('[data-image-preview] img') : null;
    if (!img) return null;
    var r = img.getBoundingClientRect(), v = vp.getBoundingClientRect();
    return { x: Math.round(Math.max(v.left + 20, Math.min(r.left + r.width / 2, v.right - 20))),
             y: Math.round(Math.max(v.top + 20, Math.min(r.top + r.height / 2, v.bottom - 20))),
             w: Math.round(r.width), natural: img.naturalWidth + 'x' + img.naturalHeight };
  },
  kind: function () {
    var vp = window.__m.activeVp();
    var host = vp ? vp.closest('[data-document-preview]') : null;
    return {
      doc: host ? host.getAttribute('data-document-preview') : null,
      bound: vp ? vp.classList.contains('dsh-pv-vp') : null,
      hasImg: !!(vp && vp.querySelector('[data-image-preview] img')),
      imgNatural: vp && vp.querySelector('img') ? vp.querySelector('img').naturalWidth + 'x' + vp.querySelector('img').naturalHeight : null,
      pdfPages: vp ? vp.querySelectorAll('[data-pdf-page]').length : 0,
      hasPre: !!(vp && vp.querySelector('pre, [data-textpreview-plain]'))
    };
  },
  badge: function () { var b = document.getElementById('dsh-pv-badge'); return b ? b.textContent : null; }
}; 'ok'`

async function main() {
  const profile = join(tmpdir(), 'dsh-imgmenu-' + Date.now())
  mkdirSync(profile, { recursive: true })
  const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--window-size=1440,900', '--no-first-run', 'about:blank'], { stdio: 'ignore' })
  try {
    let list = null
    for (let i = 0; i < 80; i++) { try { list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (list.some((t) => t.type === 'page')) break } catch { } await sleep(250) }
    const cdp = await Cdp.connect(list.find((t) => t.type === 'page').webSocketDebuggerUrl)
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Network.enable')
    const ck = mintCookie()
    await cdp.send('Network.setCookie', { name: ck.name, value: ck.value, domain: '127.0.0.1', path: '/', httpOnly: true })

    // 假宿主桥 + 注入脚本：都挂在「每次文档创建时」，这样重载后自动生效
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
      source: `(() => {
        window.__sent = [];
        window.__handlers = [];
        window.chrome = window.chrome || {};
        window.chrome.webview = {
          postMessage: function (s) { window.__sent.push(s); },
          addEventListener: function (t, fn) { if (t === 'message') window.__handlers.push(fn); }
        };
        window.__emit = function (obj) { window.__handlers.forEach(function (fn) { fn({ data: obj }); }); };
      })();`
    })
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: readFileSync(SCRIPT, 'utf8') })

    const openFiles = async () => {
      await cdp.eval(`(() => {
        const byLabel = (t) => [...document.querySelectorAll('button[aria-label]')].find(b => (b.getAttribute('aria-label') || '') === t);
        const vis = (b) => { const s = getComputedStyle(b); const r = b.getBoundingClientRect(); return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 1; };
        const o = byLabel('打开右侧边栏'); if (o && vis(o)) o.click();
        return true;
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
    }
    const navTo = async (steps) => {
      let p = await cdp.eval('window.__m.root()')
      for (const step of steps) {
        const row = await cdp.eval(`window.__m.nav(${JSON.stringify(step)}, ${JSON.stringify(p)})`)
        if (!row || row.err) return { err: row && row.err || 'not found', step, under: p }
        const isFile = row.entry === 'file'
        if (!isFile && row.expanded) { p = row.path; continue }
        await cdp.click(row.x, row.y)
        await sleep(isFile ? 3000 : 1200)
        if (!isFile) p = row.path
      }
      return { ok: true, path: p }
    }
    // 每个用例：关掉上一轮留下的预览标签（回到「只开着一个预览」的干净状态）
    const closePreviewTabs = async () => {
      const n = await cdp.eval(`(() => {
        const tabs = [...document.querySelectorAll('[data-dockkit-tab]')].filter((t) => {
          const title = (t.getAttribute('data-dockkit-tab-title') || t.textContent || '').trim();
          return title && title !== '文件' && t.querySelector('[data-dockkit-tab-close]');
        });
        tabs.forEach((t) => { const c = t.querySelector('[data-dockkit-tab-close]'); if (c) c.click(); });
        return tabs.length;
      })()`)
      await sleep(800)
      return n
    }
    const openCase = async (steps) => {
      await closePreviewTabs()
      await cdp.eval(HELPERS)
      return navTo(steps)
    }
    const sentJson = () => cdp.eval('window.__sent.map(function (s) { return JSON.parse(s); })').then((a) => a || [])

    // 第一次：登录后等界面起来 → 打开右栏的「工作区文件」标签
    await cdp.send('Page.navigate', { url: 'http://127.0.0.1:3080/' })
    await sleep(9000)
    await cdp.eval(HELPERS)
    await openFiles()
    console.log('文件树根:', await cdp.eval('window.__m.root()'))

    /* ================= 用例 1：大图 ================= */
    console.log('【用例 1】大图 banner.png')
    const c1 = await openCase(['dsh-desktop', 'docs', 'banner.png'])
    console.log('  导航:', JSON.stringify(c1))
    const k1 = await cdp.eval('window.__m.kind()')
    console.log('  预览:', JSON.stringify(k1))
    check('大图预览绑定成功（可缩放）', k1.bound === true, k1)
    const p1 = await cdp.eval('window.__m.imgPos()')
    await cdp.rightClick(p1.x, p1.y)
    const m1 = await cdp.eval('window.__m.menu()')
    console.log('  菜单:', JSON.stringify(m1))
    check('右键弹出自己的菜单（挂在 body 上）', !!m1 && m1.inBody === true, m1)
    check('菜单项齐全（保存 / 复制图片 / 复制路径 / 适应宽度 / 实际大小 / 显示）',
      !!m1 && m1.items.some((t) => t.startsWith('保存到')) && m1.items.some((t) => t.startsWith('复制图片')) &&
      m1.items.some((t) => t.startsWith('复制文件路径')) && m1.items.some((t) => t.startsWith('适应宽度')) &&
      m1.items.some((t) => t.includes('实际大小')) && m1.items.some((t) => t.includes('在资源管理器中显示')), m1 && m1.items)
    check('菜单出现在光标附近且完整在窗口内',
      !!m1 && m1.rect[0] >= 0 && m1.rect[1] >= 0 && m1.rect[0] + m1.rect[2] <= 1440 && m1.rect[1] + m1.rect[3] <= 900, m1 && m1.rect)

    // 保存到…
    const savePos = await cdp.eval(`window.__m.itemPos('保存到')`)
    await cdp.click(savePos.x, savePos.y)
    await sleep(300)
    const sent1 = await sentJson()
    console.log('  发出:', JSON.stringify(sent1.filter((s) => s.type !== 'dsh-preview-bound')))
    const saveMsg = sent1.find((s) => s.type === 'dsh-image-save')
    check('点「保存到…」把保存请求发给宿主', !!saveMsg)
    check('送出的绝对路径 = 刚打开的那个文件',
      !!saveMsg && /^[A-Za-z]:[\\/]/.test(decB64(saveMsg.pathB64)) && decB64(saveMsg.pathB64).endsWith('docs\\banner.png'), decB64(saveMsg && saveMsg.pathB64))
    check('送出的文件名正确', decB64(saveMsg && saveMsg.nameB64) === 'banner.png', decB64(saveMsg && saveMsg.nameB64))
    check('点击后菜单立即关闭', (await cdp.eval('window.__m.menu()')) === null)

    // 宿主回执
    const savedPath = 'C:\\Users\\twinblade\\Desktop\\banner.png'
    await cdp.eval(`window.__emit(${JSON.stringify({ type: 'dsh-image-save-result', requestId: saveMsg.requestId, ok: true, pathB64: Buffer.from(savedPath, 'utf8').toString('base64') })})`)
    await sleep(200)
    const badge = await cdp.eval('window.__m.badge()')
    check('回执后提示「已保存：<路径>」', !!badge && badge.indexOf('已保存') === 0 && badge.indexOf('banner.png') > 0, badge)
    await cdp.eval(`window.__emit({ type: 'dsh-image-save-result', requestId: 'x', ok: false, reason: 'cancelled' })`)
    await sleep(150)
    check('取消时提示「已取消保存」', (await cdp.eval('window.__m.badge()')) === '已取消保存')
    await cdp.eval(`window.__emit(${JSON.stringify({ type: 'dsh-image-save-result', requestId: 'y', ok: false, reason: 'error', messageB64: Buffer.from('磁盘已满', 'utf8').toString('base64') })})`)
    await sleep(150)
    check('失败时原文显示宿主错误（中文不乱码）', String(await cdp.eval('window.__m.badge()')).indexOf('磁盘已满') > 0, await cdp.eval('window.__m.badge()'))

    // Esc / Ctrl+S / 复制图片 / 复制路径
    await cdp.rightClick(p1.x, p1.y)
    await cdp.key('Escape', 'Escape', 27)
    check('Esc 关闭菜单', (await cdp.eval('window.__m.menu()')) === null)

    await cdp.eval('window.__sent.length = 0')
    await cdp.key('s', 'KeyS', 83, 2)
    await sleep(250)
    check('图片预览里 Ctrl+S 直接保存（不用先开菜单）', (await sentJson()).some((s) => s.type === 'dsh-image-save'))

    await cdp.rightClick(p1.x, p1.y)
    await cdp.click((await cdp.eval(`window.__m.itemPos('复制图片')`)).x, (await cdp.eval(`window.__m.itemPos('复制图片')`)).y)
    await sleep(250)
    const copyMsg = (await sentJson()).find((s) => s.type === 'dsh-copy-image')
    check('「复制图片」也走宿主（拿原文件，剪贴板里是真图 + 文件）',
      !!copyMsg && decB64(copyMsg.pathB64).endsWith('banner.png'), decB64(copyMsg && copyMsg.pathB64))

    await cdp.rightClick(p1.x, p1.y)
    await cdp.key('ArrowDown', 'ArrowDown', 40)
    await cdp.key('ArrowDown', 'ArrowDown', 40)
    check('方向键可以在菜单项之间移动（高亮）',
      (await cdp.eval(`!!document.querySelector('#dsh-pv-menu .dshm-mi.dshm-focus')`)) === true)
    await cdp.key('Escape', 'Escape', 27)

    /* ================= 用例 2：小图（未绑定缩放） ================= */
    console.log('\n【用例 2】小图 icon-source.png（225×225）')
    await openCase(['dsh-desktop', 'icon-source.png'])
    const k2 = await cdp.eval('window.__m.kind()')
    console.log('  预览:', JSON.stringify(k2))
    check('小图不会被缩放增强绑定（240px 阈值仍生效）', k2.bound === false, k2)
    const p2 = await cdp.eval('window.__m.imgPos()')
    check('小图也能定位到', !!p2, p2)
    await cdp.rightClick(p2.x, p2.y)
    const m2 = await cdp.eval('window.__m.menu()')
    console.log('  小图菜单:', JSON.stringify(m2))
    check('小图也有右键菜单（保存可用）', !!m2 && m2.items.some((t) => t.startsWith('保存到')), m2)
    check('小图菜单里没有缩放项（没绑定就不提供）', !!m2 && !m2.items.some((t) => t.startsWith('适应宽度')), m2 && m2.items)
    await cdp.key('Escape', 'Escape', 27)

    /* ================= 用例 3：PDF 不接管 ================= */
    console.log('\n【用例 3】PDF 预览')
    await openCase(['dsh-desktop', 'tools', 'preview-probe', 'fixtures', 'three-pages.pdf'])
    const k3 = await cdp.eval('window.__m.kind()')
    console.log('  预览:', JSON.stringify(k3))
    check('PDF 预览已就位', k3.pdfPages > 0, k3)
    const pdfPos = await cdp.eval(`(() => { var vp = window.__m.activeVp(); var c = vp && vp.querySelector('[data-pdf-page] canvas'); if (!c) return null; var r = c.getBoundingClientRect(); return { x: Math.round(r.left + 40), y: Math.round(r.top + 40) }; })()`)
    await cdp.rightClick(pdfPos.x, pdfPos.y)
    check('PDF 上右键不弹我们的菜单', (await cdp.eval('window.__m.menu()')) === null)
    const pdfPrevented = await cdp.eval(`(() => { var vp = window.__m.activeVp(); var c = vp.querySelector('[data-pdf-page] canvas'); var r = c.getBoundingClientRect(); var ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: r.left + 40, clientY: r.top + 40 }); c.dispatchEvent(ev); return ev.defaultPrevented; })()`)
    check('PDF 的右键没有被我们 preventDefault（产品菜单照常）', pdfPrevented === false, pdfPrevented)

    /* ================= 用例 4：文本不接管 ================= */
    console.log('\n【用例 4】文本预览 README.md')
    await openCase(['dsh-desktop', 'README.md'])
    const k4 = await cdp.eval('window.__m.kind()')
    console.log('  预览:', JSON.stringify(k4))
    check('文本预览不绑定', k4.bound === false, k4)
    const textPrevented = await cdp.eval(`(() => { var vp = window.__m.activeVp(); if (!vp) return 'no-vp'; var r = vp.getBoundingClientRect(); var ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: r.left + 40, clientY: r.top + 40 }); vp.dispatchEvent(ev); return ev.defaultPrevented; })()`)
    check('文本预览的右键没有被接管', textPrevented === false, textPrevented)
    check('文本预览不弹我们的菜单', (await cdp.eval('window.__m.menu()')) === null)

    const errs = cdp.events.filter((e) => e.method === 'Runtime.exceptionThrown')
    console.log('\n未捕获异常 =', errs.length || 0)
    check('零未捕获异常', (errs.length || 0) === 0, (errs[0] && errs[0].params.exceptionDetails.text) || '')
  } finally {
    try { edge.kill() } catch { }
  }
  console.log('\n结果: 通过 ' + pass + ' / 失败 ' + fail)
  process.exit(fail ? 1 : 0)
}
main().catch((e) => { console.error('测试脚本自身出错:', e.message); process.exit(2) })
