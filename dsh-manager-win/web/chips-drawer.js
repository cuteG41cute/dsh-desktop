/*
 * chips-drawer.js — 顶栏插件芯片收进一个「插件」芯片（桌面窗口版）
 *
 * 结构按用户提的思路：把「插件」做成工具区里的**一枚普通芯片**，
 * 其余芯片在收起时按结构隐藏（不逐个打标记，重渲染也不会失效）；
 * 展开时把兄弟芯片以 fixed 竖排浮到药丸下方，点开仍是它们自己的原生面板。
 */
(function () {
  if (window.__dshChipsDrawer) return;
  window.__dshChipsDrawer = true;

  var UTIL_SEL = 'div[class*="headerUtilities"], div[class*="HeaderUtilities"]';
  var BREAK = 1500;

  function post(obj) {
    try {
      if (window.chrome && chrome.webview && chrome.webview.postMessage) {
        chrome.webview.postMessage(JSON.stringify(obj));
      }
    } catch (_) { }
  }

  function installStyle() {
    try {
      if (document.getElementById('dshcd-style')) return;
      var host = document.head || document.documentElement || document.body;
      if (!host) return;
      var s = document.createElement('style');
      s.id = 'dshcd-style';
      s.textContent = [
        'body.dshcd-on [data-dshcd-item]{display:none !important;}',
        'body.dshcd-on.dshcd-open [data-dshcd-item]{',
        '  display:inline-flex !important;position:fixed !important;right:8px !important;left:auto !important;',
        '  z-index:70 !important;width:168px !important;justify-content:flex-start !important;',
        '  background:rgba(255,255,255,.98) !important;box-shadow:0 4px 16px rgba(0,0,0,.18) !important;',
        '  border-radius:9px !important;}',
        'body.dsh-dark.dshcd-on.dshcd-open [data-dshcd-item]{background:rgba(30,30,34,.97) !important;}',
        '#dshcd-pill{font:inherit;font-size:11px;line-height:18px;padding:4px 10px;border-radius:999px;',
        '  border:1px solid rgba(128,128,128,.35);background:rgba(255,255,255,.92);color:#555;',
        '  cursor:pointer;white-space:nowrap;display:none;margin-right:6px;}',
        'body.dsh-dark #dshcd-pill{background:rgba(30,30,34,.92);color:#ddd;}',
        '#dshcd-pill.dshcd-show{display:inline-block;}',
        '#dshcd-pill.dshcd-open{border-color:#4d6bfe;color:#4d6bfe;}',
        'body.dshcd-floating #dshcd-pill{position:fixed;top:12px;right:12px;z-index:71;display:inline-block;}',
      ].join('\n');
      host.appendChild(s);
    } catch (e) { post({ dshcd: 'style-error', m: String((e && e.message) || e) }); }
  }

  var CHIP_RE = /^(时间戳|网络|朗读|记忆库|备份|语音|记忆)/;

  /* 优先用产品自己的工具区；类名对不上时，用「带芯片文案的按钮」的公共父元素兜底 */
  function utilities() {
    var util = document.querySelector(UTIL_SEL);
    if (util) return util;
    var bs = document.querySelectorAll('button, [role="button"], a[href]');
    var hit = null;
    for (var i = 0; i < bs.length; i++) {
      var b = bs[i];
      if (b.id === 'dshcd-pill') continue;
      var t = (b.innerText || '').trim();
      if (!t || !CHIP_RE.test(t)) continue;
      var r = b.getBoundingClientRect();
      if (r.width < 6 || r.top > 90) continue;
      hit = b;
      break;
    }
    if (!hit) return null;
    var host = hit.parentElement;
    while (host && host !== document.body) {
      var n = 0;
      for (var k = 0; k < host.children.length; k++) {
        var ct = (host.children[k].innerText || '').trim();
        if (ct && CHIP_RE.test(ct)) n++;
      }
      if (n >= 2) return host;
      host = host.parentElement;
    }
    return hit.parentElement;
  }

  function siblings(util) {
    var out = [];
    if (!util) return out;
    for (var i = 0; i < util.children.length; i++) {
      var k = util.children[i];
      if (k.id === 'dshcd-pill') continue;
      var t = (k.innerText || '').trim();
      if (!t) continue;
      /* 有工具区时任意带文字的控件都算芯片；兜底容器里只认芯片文案，避免误藏侧栏按钮 */
      var official = !!document.querySelector(UTIL_SEL);
      if (!official && !CHIP_RE.test(t)) continue;
      k.setAttribute('data-dshcd-item', '1');
      out.push(k);
    }
    return out;
  }

  var pill = null;

  function ensurePill() {
    if (pill && pill.parentElement) return pill;
    var util = utilities();
    if (!pill) {
      pill = document.createElement('button');
      pill.id = 'dshcd-pill';
      pill.type = 'button';
      pill.textContent = '插件';
      pill.addEventListener('click', function (e) {
        e.stopPropagation();
        setOpen(!document.body.classList.contains('dshcd-open'));
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') setOpen(false);
      });
    }
    if (util) {
      util.appendChild(pill);
      document.body.classList.remove('dshcd-floating');
    } else {
      document.body.appendChild(pill);
      document.body.classList.add('dshcd-floating');
    }
    return pill;
  }

  function layout() {
    if (!pill) return;
    var items = siblings(utilities());
    var top = pill.getBoundingClientRect().bottom + 8;
    for (var i = 0; i < items.length; i++) {
      items[i].style.setProperty('top', Math.round(top + i * 36) + 'px', 'important');
    }
  }

  function setOpen(open) {
    document.body.classList.toggle('dshcd-open', open);
    if (pill) pill.classList.toggle('dshcd-open', open);
    if (open) layout();
    post({ dshcd: 'panel', open: open, items: siblings(utilities()).length });
  }

  var lastDiag = 0;
  function diag() {
    var now = Date.now();
    if (now - lastDiag < 15000) return;
    lastDiag = now;
    var util = utilities();
    post({
      dshcd: 'diag',
      util: !!util,
      width: innerWidth,
      siblings: siblings(util).length,
      pillInUtil: !!(pill && util && pill.parentElement === util),
      on: document.body.classList.contains('dshcd-on'),
    });
  }

  var lastCollapseWidth = 0;

  function apply() {
    if (!document.body) return;
    var util = utilities();
    var items = siblings(util);
    var narrow = innerWidth < BREAK;
    var hide = narrow;
    if (!hide && document.body.classList.contains('dshcd-on')) {
      hide = innerWidth <= lastCollapseWidth + 40;
    }
    var on = hide && items.length >= 1 && !!util;
    if (on) {
      lastCollapseWidth = Math.max(0, innerWidth);
      ensurePill();
      if (pill) pill.textContent = '插件 ' + items.length;
      document.body.classList.add('dshcd-on');
      if (pill) pill.classList.add('dshcd-show');
      if (document.body.classList.contains('dshcd-open')) layout();
    } else {
      document.body.classList.remove('dshcd-on');
      document.body.classList.remove('dshcd-open');
      if (pill) {
        pill.classList.remove('dshcd-show');
        pill.classList.remove('dshcd-open');
        if (pill.parentElement) pill.parentElement.removeChild(pill);
      }
    }
    diag();
  }

  var timer = null;
  function schedule() {
    if (timer) return;
    timer = setTimeout(function () {
      timer = null;
      try { apply(); } catch (e) { post({ dshcd: 'apply-error', m: String((e && e.message) || e) }); }
    }, 150);
  }

  function boot() {
    if (!document.body) { setTimeout(boot, 60); return; }
    installStyle();
    document.body.classList.toggle('dsh-dark', document.body.hasAttribute('data-ds-dark-theme'));
    try { apply(); } catch (e) { post({ dshcd: 'apply-error', m: String((e && e.message) || e) }); }
    setInterval(function () {
      document.body.classList.toggle('dsh-dark', document.body.hasAttribute('data-ds-dark-theme'));
      try { apply(); } catch (e) { post({ dshcd: 'apply-error', m: String((e && e.message) || e) }); }
    }, 1200);
    window.addEventListener('resize', schedule);
  }

  try { boot(); } catch (e) { post({ dshcd: 'fatal', m: String((e && e.message) || e) }); }
})();
