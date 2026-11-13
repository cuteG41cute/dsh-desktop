/*
 * chips-drawer.js — 顶栏插件芯片在窗口变窄时收进「插件」抽屉
 *
 * 背景：DSH 的会话头部工具区（headerUtilities）里堆着各家插件的芯片
 * （时间戳 / 网络 / 朗读 / 记忆库 / 备份 …）。窗口一窄，它们会把
 * 标题、后台任务、右侧栏按钮挤到看不见。
 *
 * 做法：窗口宽度小于断点时，把工具区里「带可见文字的控件」标记为芯片
 * 并隐藏，在顶栏右侧放一个「插件 N」药丸；点开是竖排抽屉，每项点击
 * 转发给原芯片（不改产品 DOM 结构，不抢事件）。
 *
 * 只在我们的桌面窗口里注入；手机端桥另有一套（dshm-plugin-toggle），
 * 检测到它在显示就完全不抢活。
 */
(function () {
  if (window.__dshChipsDrawer) return;
  window.__dshChipsDrawer = true;

  var BREAK = 1180;          // 窄于此宽度才收
  var MIN_CHIPS = 2;         // 至少两枚才值得收
  var style = document.createElement('style');
  style.id = 'dshcd-style';
  style.textContent = [
    'body.dshcd-on [data-dshcd-chip]{display:none !important;}',
    '#dshcd-pill{position:fixed;z-index:2147483000;height:26px;padding:0 10px;border-radius:8px;',
    '  border:1px solid rgba(128,128,128,.45);background:rgba(20,20,24,.06);color:inherit;',
    '  font:inherit;font-size:11px;line-height:24px;cursor:pointer;display:none;align-items:center;gap:5px;}',
    '#dshcd-pill.dshcd-show{display:inline-flex;}',
    '#dshcd-pill.dshcd-open{border-color:rgba(128,128,128,.8);}',
    '#dshcd-panel{position:fixed;z-index:2147483000;min-width:150px;max-width:280px;padding:6px;',
    '  border-radius:10px;border:1px solid rgba(128,128,128,.35);background:rgba(255,255,255,.96);',
    '  color:#111;box-shadow:0 8px 24px rgba(0,0,0,.18);display:none;flex-direction:column;gap:2px;}',
    'body.dsh-dark #dshcd-panel{background:rgba(30,30,34,.97);color:#eee;}',
    '#dshcd-panel.dshcd-show{display:flex;}',
    '#dshcd-panel button{all:unset;box-sizing:border-box;display:block;width:100%;padding:6px 8px;',
    '  border-radius:7px;font:inherit;font-size:11px;cursor:pointer;white-space:nowrap;overflow:hidden;',
    '  text-overflow:ellipsis;color:inherit;}',
    '#dshcd-panel button:hover{background:rgba(128,128,128,.18);}',
  ].join('\n');
  if (!document.getElementById('dshcd-style')) (document.head || document.documentElement).appendChild(style);

  var pill = null, panel = null;

  function utilities() { return document.querySelector('div[class*="_headerUtilities"]'); }

  function inFloatingPanel(node, util) {
    var p = node.parentElement;
    while (p && p !== util) {
      if (window.getComputedStyle(p).position === 'fixed') return true;
      p = p.parentElement;
    }
    return false;
  }

  function mobilePillShowing() {
    var p = document.getElementById('dshm-plugin-toggle');
    if (!p) return false;
    var r = p.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  function collectChips() {
    var util = utilities();
    var out = [];
    if (!util) return out;
    var nodes = util.querySelectorAll('button, [role="button"], a[href]');
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.id && n.id.indexOf('dshcd-') === 0) continue;
      if (n.id && n.id.indexOf('dshm-') === 0) continue;
      var label = (n.innerText || n.textContent || '').trim();
      if (!label) continue;
      if (inFloatingPanel(n, util)) continue;
      out.push(n);
    }
    return out;
  }

  function ensurePill() {
    if (pill) return pill;
    pill = document.createElement('button');
    pill.id = 'dshcd-pill';
    pill.type = 'button';
    pill.textContent = '插件';
    pill.title = '收起顶栏芯片';
    pill.addEventListener('click', function (e) {
      e.stopPropagation();
      togglePanel(panel && panel.classList.contains('dshcd-show') ? false : true);
    });
    document.body.appendChild(pill);

    panel = document.createElement('div');
    panel.id = 'dshcd-panel';
    document.body.appendChild(panel);

    document.addEventListener('click', function (e) {
      if (panel && panel.classList.contains('dshcd-show') &&
          !panel.contains(e.target) && e.target !== pill) {
        togglePanel(false);
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') togglePanel(false);
    });
    window.addEventListener('resize', schedule);
    return pill;
  }

  function placePill() {
    if (!pill) return;
    var corner = document.querySelector('div[class*="_headerCorner"]');
    var r = corner ? corner.getBoundingClientRect() : null;
    if (r && r.width > 0) {
      pill.style.top = Math.max(2, Math.round(r.top + 4)) + 'px';
      pill.style.right = Math.max(4, Math.round(window.innerWidth - r.left + 8)) + 'px';
      return;
    }
    var util = utilities();
    if (util) {
      var u = util.getBoundingClientRect();
      pill.style.top = Math.max(2, Math.round(u.top + 4)) + 'px';
      pill.style.right = Math.max(6, Math.round(window.innerWidth - u.right + 6)) + 'px';
    }
  }

  function renderPanel(chips) {
    if (!panel) return;
    panel.innerHTML = '';
    for (var i = 0; i < chips.length; i++) {
      (function (chip) {
        var b = document.createElement('button');
        b.type = 'button';
        var label = (chip.innerText || chip.textContent || '').trim();
        b.textContent = label || '未命名';
        b.title = label;
        b.addEventListener('click', function (e) {
          e.stopPropagation();
          try { chip.click(); } catch (_) { }
          refresh();   // 芯片文案（开/关、备份大小）会变，点完刷新一次
        });
        panel.appendChild(b);
      })(chips[i]);
    }
  }

  function togglePanel(open) {
    if (!panel) return;
    if (open) {
      var chips = collectChips();
      renderPanel(chips);
      var r = pill.getBoundingClientRect();
      panel.style.top = Math.round(r.bottom + 6) + 'px';
      panel.style.right = Math.max(6, Math.round(window.innerWidth - r.right)) + 'px';
      panel.classList.add('dshcd-show');
      if (pill) pill.classList.add('dshcd-open');
    } else {
      panel.classList.remove('dshcd-show');
      if (pill) pill.classList.remove('dshcd-open');
    }
  }

  function apply() {
    if (mobilePillShowing()) {          // 手机端桥已经接管，别抢
      if (pill) pill.classList.remove('dshcd-show');
      if (panel) panel.classList.remove('dshcd-show');
      document.body.classList.remove('dshcd-on');
      return;
    }
    var chips = collectChips();
    var narrow = window.innerWidth < BREAK;
    var on = narrow && chips.length >= MIN_CHIPS;
    if (on) {
      for (var i = 0; i < chips.length; i++) chips[i].setAttribute('data-dshcd-chip', '1');
      document.body.classList.add('dshcd-on');
      ensurePill();
      pill.textContent = '插件 ' + chips.length;
      pill.classList.add('dshcd-show');
      placePill();
      if (panel && panel.classList.contains('dshcd-show')) renderPanel(chips);
    } else {
      var tagged = document.querySelectorAll('[data-dshcd-chip]');
      for (var j = 0; j < tagged.length; j++) tagged[j].removeAttribute('data-dshcd-chip');
      document.body.classList.remove('dshcd-on');
      if (pill) pill.classList.remove('dshcd-show');
      if (panel) panel.classList.remove('dshcd-show');
    }
  }

  function refresh() {
    try { apply(); } catch (_) { }
  }

  var timer = null;
  function schedule() {
    if (timer) return;
    timer = setTimeout(function () { timer = null; refresh(); }, 150);
  }

  function boot() {
    if (!document.body) { setTimeout(boot, 60); return; }
    var dark = document.body.hasAttribute('data-ds-dark-theme');
    document.body.classList.toggle('dsh-dark', dark);
    refresh();
    setInterval(refresh, 1200);
    window.addEventListener('resize', schedule);
  }

  boot();
})();
