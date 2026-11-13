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

  function post(obj) {
    try {
      if (window.chrome && chrome.webview && chrome.webview.postMessage) {
        chrome.webview.postMessage(JSON.stringify(obj));
      }
    } catch (_) { }
  }
  post({ dshcd: 'boot', ready: document.readyState, body: !!document.body });

  var BREAK = 1500;          // 窄于此宽度才收（1440 时顶栏已经放不下了）
  var MIN_CHIPS = 2;         // 至少两枚才值得收
  var STYLE_TEXT = [
    'body.dshcd-on [data-dshcd-chip]{display:none !important;}',
    'body.dshcd-on.dshcd-open [data-dshcd-chip]{display:inline-flex !important;',
    '  position:fixed !important; right:12px !important; z-index:2147483001 !important;}',
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
  ].join('\n');;

  function installStyle() {
    try {
      if (document.getElementById('dshcd-style')) return true;
      var host0 = document.head || document.documentElement || document.body;
      if (!host0) return false;
      var s = document.createElement('style');
      s.id = 'dshcd-style';
      s.textContent = STYLE_TEXT;
      host0.appendChild(s);
      return true;
    } catch (e) { post({ dshcd: 'style-error', m: String((e && e.message) || e) }); return false; }
  }
  installStyle();


  var pill = null;

  function utilities() {
    return document.querySelector('div[class*="headerUtilities"], div[class*="HeaderUtilities"], [class*="_headerUtilities"]');
  }
  var CHIP_TEXT_RE = /^(时间戳|网络|朗读|记忆库|备份|语音|记忆)/;
  function fallbackChips() {
    var out = [];
    var bs = document.querySelectorAll('button, [role="button"], a[href]');
    for (var i = 0; i < bs.length; i++) {
      var b = bs[i];
      if (b.id && (b.id.indexOf('dshcd-') === 0 || b.id.indexOf('dshm-') === 0)) continue;
      var t = (b.innerText || b.textContent || '').trim();
      if (!t || t.length > 24) continue;
      if (!CHIP_TEXT_RE.test(t)) continue;
      /* 注意：芯片被我们 display:none 之后 innerText 会变空、宽度变 0，
         这里不能再按可见宽度过滤，否则第二帧会把芯片当成不存在而反复闪。 */
      out.push(b);
    }
    return out;
  }

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
    if (!util) return fallbackChips();
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
      toggleStack(!document.body.classList.contains('dshcd-open'));
    });
    document.body.appendChild(pill);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') toggleStack(false);
    });
    window.addEventListener('resize', schedule);
    return pill;
  }

  function topRightButtons() {
    var out = [];
    var bs = document.querySelectorAll('button, [role="button"]');
    for (var i = 0; i < bs.length; i++) {
      var b = bs[i];
      if (b.id && b.id.indexOf('dshcd-') === 0) continue;
      if (b.hasAttribute('data-dshcd-chip')) continue;
      var r = b.getBoundingClientRect();
      if (r.width < 6 || r.height < 6) continue;
      if (r.top > 90) continue;                       /* 只看顶栏那一行 */
      if (r.right < window.innerWidth - 320) continue; /* 只看靠右的一组 */
      out.push(r);
    }
    return out;
  }

  function placePill() {
    if (!pill) return;
    var corner = document.querySelector('div[class*="_headerCorner"]');
    var r = corner ? corner.getBoundingClientRect() : null;
    var rightLimit = null;
    if (r && r.width > 0) {
      rightLimit = r.left;
    } else {
      /* 没有 headerCorner 类名：取顶栏右侧那组按钮里最靠左的那个，药丸排在它左边 */
      var rects = topRightButtons();
      if (rects.length) {
        var minLeft = Infinity, topMin = Infinity;
        for (var i = 0; i < rects.length; i++) {
          if (rects[i].left < minLeft) minLeft = rects[i].left;
          if (rects[i].top < topMin) topMin = rects[i].top;
        }
        rightLimit = minLeft;
        pill.style.top = Math.max(2, Math.round(topMin + 3)) + 'px';
      }
    }
    if (rightLimit !== null && Math.round(window.innerWidth - rightLimit + 8) > 0) {
      pill.style.right = Math.round(window.innerWidth - rightLimit + 8) + 'px';
    }
    if (!pill.style.top) pill.style.top = '12px';
  }

  /* 展开态：把真芯片竖排固定在药丸下方（不是复制按钮），
     这样点开芯片弹出的面板仍然挂在芯片自己身上，内容/开关都在。 */
  function layoutStack() {
    if (!pill) return;
    var chips = collectChips();
    var y = pill.getBoundingClientRect().bottom + 8;
    for (var i = 0; i < chips.length; i++) {
      chips[i].style.setProperty('top', Math.round(y + i * 36) + 'px', 'important');
    }
  }

  function toggleStack(open) {
    if (!document.body) return;
    document.body.classList.toggle('dshcd-open', open);
    if (pill) pill.classList.toggle('dshcd-open', open);
    if (open) layoutStack();
  }

  function diag() {
    var now = Date.now();
    if (now - lastDiag < 30000) return;
    lastDiag = now;
    try {
      if (!(window.chrome && chrome.webview && chrome.webview.postMessage)) return;
      var util = utilities();
      var sample = [];
      var bs = document.querySelectorAll('button, [role="button"]');
      for (var i = 0; i < bs.length && sample.length < 8; i++) {
        var t = (bs[i].innerText || '').trim();
        if (t) sample.push(t.slice(0, 14));
      }
      chrome.webview.postMessage(JSON.stringify({
        dshcd: 'diag',
        util: !!util,
        utilClass: util ? String(util.className) : null,
        width: innerWidth,
        chips: collectChips().length,
        sample: sample
      }));
    } catch (_) { }
  }

  function apply() {
    if (mobilePillShowing()) {          // 手机端桥已经接管，别抢
      if (pill) pill.classList.remove('dshcd-show');
      document.body.classList.remove('dshcd-on');
      document.body.classList.remove('dshcd-open');
      return;
    }
    var chips = collectChips();
    var narrow = window.innerWidth < BREAK;
    var util0 = utilities();
    var already = document.body.classList.contains('dshcd-on');
    /* 芯片一旦被藏起来，就量不到它们的宽度/重叠了 —— 这时候沿用上一次的判断，
       直到窗口变宽超过「上次触发时的宽度 + 40」才重新评估，避免一帧藏一帧露地闪。 */
    var squeezed;
    if (narrow) squeezed = true;
    else if (already && window.innerWidth <= (lastCollapseWidth + 40)) squeezed = true;
    else squeezed = chipsOverlapHeader(util0, chips);
    var on = squeezed && chips.length >= MIN_CHIPS;
    if (on) lastCollapseWidth = Math.max(0, window.innerWidth);
    if (on) {
      for (var i = 0; i < chips.length; i++) chips[i].setAttribute('data-dshcd-chip', '1');
      document.body.classList.add('dshcd-on');
      ensurePill();
      pill.textContent = '插件 ' + chips.length;
      pill.classList.add('dshcd-show');
      placePill();
      if (document.body.classList.contains('dshcd-open')) layoutStack();
    } else {
      var tagged = document.querySelectorAll('[data-dshcd-chip]');
      for (var j = 0; j < tagged.length; j++) tagged[j].removeAttribute('data-dshcd-chip');
      document.body.classList.remove('dshcd-on');
      if (pill) pill.classList.remove('dshcd-show');
      document.body.classList.remove('dshcd-open');
    }
    diag();
  }

  function refresh() {
    try { apply(); } catch (e) { post({ dshcd: 'apply-error', m: String((e && e.message) || e) }); }
  }

  var timer = null;
  function schedule() {
    if (timer) return;
    timer = setTimeout(function () { timer = null; refresh(); }, 150);
  }

  function boot() {
    if (!document.body) { setTimeout(boot, 60); return; }
    installStyle();
    var dark = document.body.hasAttribute('data-ds-dark-theme');
    document.body.classList.toggle('dsh-dark', dark);
    refresh();
    setInterval(refresh, 1200);
    window.addEventListener('resize', schedule);
  }

  try { boot(); } catch (e) { post({ dshcd: 'fatal', m: String((e && e.message) || e) }); }
})();
