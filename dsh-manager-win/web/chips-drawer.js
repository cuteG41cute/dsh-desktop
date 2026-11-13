/*
 * chips-drawer.js — 顶栏插件芯片在窗口变窄时收进「插件」药丸（桌面窗口版）
 *
 * 逻辑与手机端 share/dsh-mobile-bridge/mobile-tweaks.js 的「插件」面板一致：
 *   1) 把顶栏工具区里「带可见文字的控件」标记成芯片（动态归集，不写死插件名）；
 *   2) 窗口放不下时，芯片 display:none，右上角出现「插件 N」药丸；
 *   3) 点药丸 → 芯片本体（不是复制品）以 position:fixed 竖排浮在药丸下方，
 *      点哪枚就弹它自己的原生面板（开关/关闭都在）；
 *   4) 再点药丸 / Esc / 点别处 → 收起。
 */
(function () {
  if (window.__dshChipsDrawer) return;
  window.__dshChipsDrawer = true;

  function post(obj) {
    try {
      if (window.chrome && chrome.webview && chrome.webview.postMessage) {
        chrome.webview.postMessage(JSON.stringify(obj));
      }
    } catch (_) { }
  }

  var BREAK = 1500;        // 窄于此宽度收起
  var MIN_CHIPS = 2;
  var CHIP_TEXT_RE = /^(时间戳|网络|朗读|记忆库|备份|语音|记忆)/;

  function installStyle() {
    try {
      if (document.getElementById('dshcd-style')) return;
      var host = document.head || document.documentElement || document.body;
      if (!host) return;
      var s = document.createElement('style');
      s.id = 'dshcd-style';
      s.textContent = [
        'body:not(.dshcd-open) [data-dshcd-chip]{display:none !important;}',
        'body.dshcd-open [data-dshcd-chip]{position:fixed !important;right:8px !important;left:auto !important;',
        '  z-index:70 !important;width:168px !important;justify-content:flex-start !important;',
        '  background:rgba(255,255,255,.98) !important;box-shadow:0 4px 16px rgba(0,0,0,.18) !important;',
        '  border-radius:9px !important;}',
        'body.dsh-dark.dshcd-open [data-dshcd-chip]{background:rgba(30,30,34,.97) !important;}',
        '#dshcd-pill{position:fixed;z-index:71;font:inherit;font-size:11px;line-height:18px;padding:4px 10px;',
        '  border-radius:999px;border:1px solid rgba(128,128,128,.35);background:rgba(255,255,255,.92);',
        '  color:#555;cursor:pointer;white-space:nowrap;box-shadow:0 2px 10px rgba(0,0,0,.12);display:none;}',
        'body.dsh-dark #dshcd-pill{background:rgba(30,30,34,.92);color:#ddd;}',
        '#dshcd-pill.dshcd-show{display:inline-block;}',
        '#dshcd-pill.dshcd-open{border-color:#4d6bfe;color:#4d6bfe;}',
      ].join('\n');
      host.appendChild(s);
    } catch (e) { post({ dshcd: 'style-error', m: String((e && e.message) || e) }); }
  }

  function utilities() {
    return document.querySelector('div[class*="headerUtilities"], div[class*="HeaderUtilities"]');
  }

  function inFloatingPanel(node, util) {
    var p = node.parentElement;
    while (p && p !== util) {
      if (window.getComputedStyle(p).position === 'fixed') return true;
      p = p.parentElement;
    }
    return false;
  }

  function textOf(node) {
    var t = (node.innerText || '').trim();
    if (!t) t = (node.textContent || '').trim();
    return t;
  }

  function collectChips() {
    /* 已经收起时只认“之前标记过的芯片”，不再重新扫描：
       否则用户点开某个插件面板后，面板里的「开关 / 关闭」按钮会被当成新芯片
       收走、做成抽屉里的条目 —— 这正是之前面板按钮消失的原因。 */
    if (document.body && document.body.classList.contains('dshcd-on')) {
      var tagged = document.querySelectorAll('[data-dshcd-chip]');
      var keep = [];
      for (var t = 0; t < tagged.length; t++) keep.push(tagged[t]);
      return keep;
    }
    var util = utilities();
    var out = [];
    if (util) {
      var nodes = util.querySelectorAll('button, [role="button"], a[href]');
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (n.id && n.id.indexOf('dshcd-') === 0) continue;
        if (n.hasAttribute('data-dshcd-chip')) { out.push(n); continue; }
        if (!(n.innerText || '').trim()) continue;
        if (inFloatingPanel(n, util)) continue;
        out.push(n);
      }
      return out;
    }
    var bs = document.querySelectorAll('button, [role="button"], a[href]');
    for (var k = 0; k < bs.length; k++) {
      var b = bs[k];
      if (b.id && b.id.indexOf('dshcd-') === 0) continue;
      if (b.hasAttribute('data-dshcd-chip')) { out.push(b); continue; }
      var t = textOf(b);
      if (!t || t.length > 24) continue;
      if (!CHIP_TEXT_RE.test(t)) continue;
      out.push(b);
    }
    return out;
  }

  function intersects(a, b) {
    return a.width > 0 && b.width > 0 &&
      a.left < b.right - 2 && a.right > b.left + 2 &&
      a.top < b.bottom - 2 && a.bottom > b.top + 2;
  }

  function squeezedByOverlap(chips) {
    if (!chips.length) return false;
    var host = chips[0].parentElement;
    for (var i = 0; i < chips.length; i++) {
      while (host && !host.contains(chips[i])) host = host.parentElement;
    }
    if (!host || !host.parentElement) return false;
    host = host.parentElement;
    var nodes = host.querySelectorAll('*');
    for (var n = 0; n < nodes.length; n++) {
      var el = nodes[n];
      if (el.hasAttribute && el.hasAttribute('data-dshcd-chip')) continue;
      if (el.querySelector && el.querySelector('[data-dshcd-chip]')) continue;
      if (el.id && el.id.indexOf('dshcd-') === 0) continue;
      var txt = (el.textContent || '').trim();
      if (!txt) continue;
      var r = el.getBoundingClientRect();
      if (r.width < 6 || r.height < 6) continue;
      for (var c = 0; c < chips.length; c++) {
        if (chips[c] === el || chips[c].contains(el)) continue;
        if (intersects(chips[c].getBoundingClientRect(), r)) return true;
      }
    }
    return false;
  }

  var pill = null;

  function ensurePill() {
    if (pill) return pill;
    pill = document.createElement('button');
    pill.id = 'dshcd-pill';
    pill.type = 'button';
    pill.textContent = '插件';
    pill.addEventListener('click', function (e) {
      e.stopPropagation();
      setPanel(!document.body.classList.contains('dshcd-open'));
    });
    document.body.appendChild(pill);
    document.addEventListener('click', function (e) {
      if (!document.body.classList.contains('dshcd-open')) return;
      if (pill && (pill === e.target || pill.contains(e.target))) return;
      var chip = e.target && e.target.closest ? e.target.closest('[data-dshcd-chip]') : null;
      if (!chip) setPanel(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setPanel(false);
    });
    window.addEventListener('resize', schedule);
    return pill;
  }

  function findMoreButton() {
    var bs = document.querySelectorAll('button, [role="button"]');
    for (var i = 0; i < bs.length; i++) {
      var b = bs[i];
      if (b.id && b.id.indexOf('dshcd-') === 0) continue;
      if (b.hasAttribute('data-dshcd-chip')) continue;
      var t = (b.innerText || '').trim();
      var aria = (b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '');
      if (!(/^(⋯|…|\.\.\.|···)$/.test(t) || /更多|more actions|更多操作/i.test(aria))) continue;
      var r = b.getBoundingClientRect();
      if (r.width < 6 || r.top > 90) continue;
      return r;
    }
    return null;
  }

  function placePill() {
    if (!pill) return;
    if (reserved) {
      var rr = reserved.getBoundingClientRect();
      pill.style.top = Math.max(2, Math.round(rr.top + (rr.height - 26) / 2)) + 'px';
      pill.style.right = '8px';
      return;
    }
    var corner = document.querySelector('div[class*="_headerCorner"]');
    var cr = corner ? corner.getBoundingClientRect() : null;
    if (cr && cr.width > 0) {
      pill.style.top = Math.max(2, Math.round(cr.top + (cr.height - 26) / 2)) + 'px';
      pill.style.right = '8px';
      return;
    }
    var more = findMoreButton();
    if (cr && cr.width > 0) {
      pill.style.top = Math.max(2, Math.round(cr.top + (cr.height - 26) / 2)) + 'px';
      pill.style.right = Math.round(window.innerWidth - cr.left + 8) + 'px';
    } else if (more) {
      pill.style.top = Math.max(2, Math.round(more.top + (more.height - 26) / 2)) + 'px';
      pill.style.right = Math.round(window.innerWidth - more.left + 8) + 'px';
    } else {
      var chips = collectChips();
      if (chips.length) {
        var r0 = chips[0].getBoundingClientRect();
        pill.style.top = Math.max(2, Math.round(r0.top + (r0.height - 26) / 2)) + 'px';
      }
      pill.style.right = '12px';
    }
    var pr = pill.getBoundingClientRect();
    var anchor = (cr && cr.width > 0) ? cr : more;
    if (anchor && pr.right > anchor.left - 2) {
      pill.style.right = (parseFloat(pill.style.right || '0') + (pr.right - anchor.left + 6)) + 'px';
    }
  }

  var reserved = null;
  var reservedStyle = '';

  /* 顶栏右侧那组控件（文件夹下拉 / ⋯ / 右侧边栏）整体左移，给药丸腾出位置，
     这样三者不会互相压住。 */
  function reserveSpace() {
    var corner = document.querySelector('div[class*="_headerCorner"]');
    var target = corner;
    if (!target) {
      var bs = document.querySelectorAll('button, [role="button"]');
      var best = null, bestRight = -1;
      for (var i = 0; i < bs.length; i++) {
        var b = bs[i];
        if (b.id && b.id.indexOf('dshcd-') === 0) continue;
        if (b.hasAttribute('data-dshcd-chip')) continue;
        var r = b.getBoundingClientRect();
        if (r.width < 6 || r.top > 90) continue;
        if (r.right > bestRight) { bestRight = r.right; best = b; }
      }
      target = best ? (best.parentElement || best) : null;
    }
    if (!target || target === reserved) return;
    if (reserved) reserved.setAttribute('style', reservedStyle);
    reserved = target;
    reservedStyle = target.getAttribute('style') || '';
    var pad = (pill ? pill.offsetWidth : 60) + 20;
    target.style.setProperty('margin-right', pad + 'px', 'important');
  }

  function releaseSpace() {
    if (!reserved) return;
    reserved.setAttribute('style', reservedStyle);
    reserved = null;
  }

  function layoutPanel() {
    if (!pill) return;
    var chips = collectChips();
    var top = pill.getBoundingClientRect().bottom + 8;
    for (var i = 0; i < chips.length; i++) {
      chips[i].style.setProperty('top', Math.round(top + i * 36) + 'px', 'important');
    }
  }

  function setPanel(open) {
    if (!document.body) return;
    document.body.classList.toggle('dshcd-open', open);
    if (pill) pill.classList.toggle('dshcd-open', open);
    if (open) layoutPanel();
  }

  var lastDiagAt = 0;
  function diag(extra) {
    var now = Date.now();
    if (now - lastDiagAt < 15000) return;
    lastDiagAt = now;
    var util = utilities();
    post({
      dshcd: 'diag',
      util: !!util,
      utilClass: util ? String(util.className) : null,
      width: window.innerWidth,
      chips: collectChips().length,
      open: document.body.classList.contains('dshcd-open'),
      extra: extra || null,
    });
  }

  var lastCollapseWidth = 0;

  function apply() {
    var chips = collectChips();
    var narrow = window.innerWidth < BREAK;
    var hide = narrow;
    if (!hide && document.body.classList.contains('dshcd-on')) {
      hide = window.innerWidth <= lastCollapseWidth + 40;
    }
    if (!hide && chips.length) hide = squeezedByOverlap(chips);
    var on = hide && chips.length >= MIN_CHIPS;

    if (on) {
      lastCollapseWidth = Math.max(0, window.innerWidth);
      for (var i = 0; i < chips.length; i++) chips[i].setAttribute('data-dshcd-chip', '1');
      document.body.classList.add('dshcd-on');
      ensurePill();
      pill.textContent = '插件 ' + chips.length;
      pill.classList.add('dshcd-show');
      reserveSpace();
      placePill();
      if (document.body.classList.contains('dshcd-open')) layoutPanel();
    } else {
      var olds = document.querySelectorAll('[data-dshcd-chip]');
      for (var j = 0; j < olds.length; j++) olds[j].removeAttribute('data-dshcd-chip');
      document.body.classList.remove('dshcd-on');
      document.body.classList.remove('dshcd-open');
      if (pill) {
        pill.classList.remove('dshcd-show');
        pill.classList.remove('dshcd-open');
      }
      releaseSpace();
    }
    diag(null);
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
