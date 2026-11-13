/*
 * chips-drawer.js — 顶栏插件芯片：收起成「插件 N」一枚，展开竖排
 *
 * 只认「插件芯片文案」（时间戳/网络/朗读/记忆库/备份/语音/记忆），
 * 文件夹下拉、⋯、右侧边栏这些产品控件一律不动、不藏、不挪。
 */
(function () {
  if (window.__dshChipsDrawer) return;
  window.__dshChipsDrawer = true;

  var BREAK = 1500;
  var CHIP_RE = /^(时间戳|网络|朗读|记忆库|备份|语音|记忆)/;

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
        'body.dshcd-on.dshcd-open [data-dshcd-item]{display:inline-flex !important;position:fixed !important;',
        '  right:8px !important;left:auto !important;z-index:70 !important;width:168px !important;',
        '  justify-content:flex-start !important;background:rgba(255,255,255,.98) !important;',
        '  box-shadow:0 4px 16px rgba(0,0,0,.18) !important;border-radius:9px !important;}',
        'body.dsh-dark.dshcd-on.dshcd-open [data-dshcd-item]{background:rgba(30,30,34,.97) !important;}',
        '#dshcd-pill{font:inherit;font-size:11px;line-height:18px;padding:4px 10px;border-radius:999px;',
        '  border:1px solid rgba(128,128,128,.35);background:rgba(255,255,255,.92);color:#555;',
        '  cursor:pointer;white-space:nowrap;display:none;margin-right:6px;}',
        'body.dsh-dark #dshcd-pill{background:rgba(30,30,34,.92);color:#ddd;}',
        '#dshcd-pill.dshcd-show{display:inline-block;}',
        '#dshcd-pill.dshcd-open{border-color:#4d6bfe;color:#4d6bfe;}',
      ].join('\n');
      host.appendChild(s);
    } catch (e) { post({ dshcd: 'style-error', m: String((e && e.message) || e) }); }
  }

  function isChip(el) {
    if (!el || el.id === 'dshcd-pill') return false;
    if (el.closest && el.closest('#dshcd-pill')) return false;
    var t = (el.innerText || el.textContent || '').trim();
    if (!t || t.length > 24) return false;
    if (!CHIP_RE.test(t)) return false;
    var r = el.getBoundingClientRect();
    if (r.width < 6 || r.height < 6) return false;
    if (r.top > 90) return false;
    return true;
  }

  function findChips() {
    var all = document.querySelectorAll('button, [role="button"], a[href]');
    var out = [];
    for (var i = 0; i < all.length; i++) {
      if (isChip(all[i])) out.push(all[i]);
    }
    return out;
  }

  function groupOf(chips) {
    if (!chips.length) return null;
    var host = chips[0].parentElement;
    for (var i = 0; i < chips.length; i++) {
      while (host && !host.contains(chips[i])) host = host.parentElement;
    }
    return host;
  }

  var pill = null;

  function ensurePill(group) {
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
    if (group && pill.parentElement !== group) group.appendChild(pill);
    return pill;
  }

  function layout() {
    if (!pill) return;
    var chips = findChips();
    var top = pill.getBoundingClientRect().bottom + 8;
    for (var i = 0; i < chips.length; i++) {
      chips[i].style.setProperty('top', Math.round(top + i * 36) + 'px', 'important');
    }
  }

  function setOpen(open) {
    document.body.classList.toggle('dshcd-open', open);
    if (pill) pill.classList.toggle('dshcd-open', open);
    if (open) layout();
  }

  var lastCollapseWidth = 0;
  var lastDiag = 0;

  function apply() {
    if (!document.body) return;
    var chips = findChips();
    var narrow = window.innerWidth < BREAK;
    var hide = narrow;
    if (!hide && document.body.classList.contains('dshcd-on')) {
      hide = window.innerWidth <= lastCollapseWidth + 40;
    }
    var on = hide && chips.length >= 1;

    if (on) {
      lastCollapseWidth = Math.max(0, window.innerWidth);
      for (var i = 0; i < chips.length; i++) chips[i].setAttribute('data-dshcd-item', '1');
      var stale = document.querySelectorAll('[data-dshcd-item]');
      for (var j = 0; j < stale.length; j++) {
        if (chips.indexOf(stale[j]) < 0) stale[j].removeAttribute('data-dshcd-item');
      }
      ensurePill(groupOf(chips));
      pill.textContent = '插件 ' + chips.length;
      pill.classList.add('dshcd-show');
      document.body.classList.add('dshcd-on');
      if (document.body.classList.contains('dshcd-open')) layout();
    } else {
      var marked = document.querySelectorAll('[data-dshcd-item]');
      for (var k = 0; k < marked.length; k++) marked[k].removeAttribute('data-dshcd-item');
      document.body.classList.remove('dshcd-on');
      document.body.classList.remove('dshcd-open');
      if (pill) {
        pill.classList.remove('dshcd-show');
        pill.classList.remove('dshcd-open');
        if (pill.parentElement) pill.parentElement.removeChild(pill);
      }
    }

    var now = Date.now();
    if (now - lastDiag > 15000) {
      lastDiag = now;
      post({
        dshcd: 'diag',
        width: window.innerWidth,
        chips: chips.length,
        texts: chips.map(function (c) { return (c.innerText || '').trim().slice(0, 12); }),
        on: document.body.classList.contains('dshcd-on'),
        open: document.body.classList.contains('dshcd-open'),
      });
    }
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
