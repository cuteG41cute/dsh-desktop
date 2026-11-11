// dsh-manager：朗读回复（类似豆包的“朗读”）。
//
// 两种用法：
//   1) 选中任意文字 → 右键 → 「朗读选中」；
//   2) 按 Ctrl+Shift+R（或点右下角小喇叭）→ 朗读“最后一段助手回复”。
//
// 语音走浏览器内置的 Web Speech API（WebView2/Chromium 用的是系统语音，免费、离线）。
// 首次加载会把可用语音数量/语言报给宿主（web.log 里能看到 dsh-tts-probe），方便排障。
(function () {
  if (window.__dshReadAloud) return;
  window.__dshReadAloud = true;

  var CHIP_ID = 'dsh-read-chip';
  var MENU_ID = 'dsh-read-menu';
  var TIP_ID = 'dsh-read-tip';

  var speaking = false;
  var current = null;
  var lastSpoken = '';
  var lastSpokenAt = 0;

  function post(msg) {
    try {
      if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
        window.chrome.webview.postMessage(JSON.stringify(msg));
      }
    } catch (e) {}
  }

  function voices() {
    try { return window.speechSynthesis ? window.speechSynthesis.getVoices() : []; } catch (e) { return []; }
  }

  function pickVoice() {
    var list = voices();
    if (!list.length) return null;
    var zh = list.filter(function (v) { return /zh|chinese|中文|普通话/i.test((v.lang || '') + ' ' + (v.name || '')); });
    var preferred = zh.filter(function (v) { return /Xiaoxiao|Yunxi|Huihui|Kangkang|Yaoyao|Xiaoyi|Neural/i.test(v.name || ''); });
    return preferred[0] || zh[0] || list[0];
  }

  function probe() {
    var list = voices();
    post({
      type: 'dsh-tts-probe',
      count: list.length,
      langs: list.slice(0, 8).map(function (v) { return (v.lang || '') + ':' + (v.name || ''); }).join(' | ')
    });
  }

  function stop() {
    try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) {}
    speaking = false;
    current = null;
    updateChip();
  }

  function tip(text) {
    var t = document.getElementById(TIP_ID);
    if (!t) {
      t = document.createElement('div');
      t.id = TIP_ID;
      t.setAttribute('style', [
        'position:fixed', 'right:18px', 'bottom:64px', 'z-index:2147483000',
        'padding:8px 12px', 'border-radius:10px', 'max-width:360px',
        'background:rgba(28,28,32,.92)', 'color:#fff',
        'font:12px/1.5 "Segoe UI","Microsoft YaHei",sans-serif',
        'box-shadow:0 10px 24px rgba(0,0,0,.28)', 'transition:opacity .25s', 'opacity:1'
      ].join(';'));
      document.body.appendChild(t);
    }
    t.textContent = text;
    t.style.opacity = '1';
    clearTimeout(tip._timer);
    tip._timer = setTimeout(function () { t.style.opacity = '0'; }, 2200);
  }

  function speak(text, title) {
    text = (text || '').replace(/\s+\n/g, '\n').trim();
    if (!text) { tip('没有可朗读的文字'); return; }
    var synth = window.speechSynthesis;
    if (!synth) { tip('当前窗口不支持系统语音（speechSynthesis 不可用）'); return; }
    if (text.length > 4000) text = text.slice(0, 4000) + '……';

    stop();
    var u = new SpeechSynthesisUtterance(text);
    var v = pickVoice();
    if (v) { u.voice = v; u.lang = v.lang || 'zh-CN'; } else { u.lang = 'zh-CN'; }
    u.rate = 1.0;
    u.pitch = 1.0;
    u.onstart = function () { speaking = true; current = u; updateChip(); tip('正在朗读：' + (title || '选中内容')); };
    u.onend = function () { speaking = false; current = null; updateChip(); };
    u.onerror = function (e) { speaking = false; current = null; updateChip(); tip('朗读失败：' + (e && e.error ? e.error : '未知错误')); };
    try { synth.speak(u); } catch (e) { tip('朗读失败：' + e.message); }
  }

  // ---- 找“最后一段助手回复”（启发式：可见、文本较长、不是输入框/工具条） ----
  function lastReplyText() {
    var best = null;
    var bestScore = -1;
    var nodes = document.querySelectorAll('div,p,li,section,article');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!el.offsetParent) continue;                       // 不可见
      if (el.closest('textarea,input,button,[contenteditable="true"]')) continue;
      if (el.closest('#' + CHIP_ID) || el.closest('#' + MENU_ID)) continue;
      var text = (el.innerText || '').trim();
      if (text.length < 30) continue;
      if (/^(发送消息|新建|插件|自动化任务|更多|我的实例)/.test(text)) continue;
      // 越靠下、文本越长越可能是“最后一条回复”
      var r = el.getBoundingClientRect();
      var score = text.length + Math.max(0, r.top) * 2;
      if (score > bestScore) { bestScore = score; best = text; }
    }
    return best;
  }

  function speakLastReply() {
    var text = lastReplyText();
    if (!text) { tip('没找到可朗读的回复，先选中文字右键朗读试试'); return; }
    speak(text, '最后一条回复');
  }

  // ---- 右下角小喇叭 ----
  function updateChip() {
    var chip = document.getElementById(CHIP_ID);
    if (!chip) return;
    chip.textContent = speaking ? '⏹' : '🔊';
    chip.title = speaking ? '停止朗读（Esc）' : '朗读最后一条回复（Ctrl+Shift+R）';
    chip.style.background = speaking ? 'rgba(56,132,255,.92)' : 'rgba(28,28,32,.72)';
  }

  function addChip() {
    if (document.getElementById(CHIP_ID)) return;
    var chip = document.createElement('button');
    chip.id = CHIP_ID;
    chip.setAttribute('style', [
      'position:fixed', 'right:18px', 'bottom:18px', 'z-index:2147483000',
      'width:38px', 'height:38px', 'border-radius:19px', 'border:0',
      'cursor:pointer', 'color:#fff', 'font-size:17px', 'line-height:38px',
      'text-align:center', 'background:rgba(28,28,32,.72)',
      'box-shadow:0 8px 20px rgba(0,0,0,.25)'
    ].join(';'));
    chip.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      if (speaking) stop(); else speakLastReply();
    });
    document.body.appendChild(chip);
    updateChip();
  }

  // ---- 选中文字右键菜单 ----
  function closeMenu() {
    var m = document.getElementById(MENU_ID);
    if (m) m.remove();
  }

  function showSelectionMenu(x, y, text) {
    closeMenu();
    var menu = document.createElement('div');
    menu.id = MENU_ID;
    menu.setAttribute('style', [
      'position:fixed', 'z-index:2147483001', 'min-width:150px', 'padding:6px',
      'border-radius:10px', 'background:rgba(255,255,255,.98)',
      'border:1px solid rgba(0,0,0,.10)', 'box-shadow:0 12px 28px rgba(0,0,0,.16)',
      'font:13px/1.4 "Segoe UI","Microsoft YaHei",sans-serif', 'color:#1b1b1f'
    ].join(';'));

    function row(label, fn) {
      var r = document.createElement('div');
      r.textContent = label;
      r.setAttribute('style', 'padding:7px 12px;border-radius:7px;cursor:pointer;white-space:nowrap');
      r.addEventListener('mouseenter', function () { r.style.background = 'rgba(0,0,0,.06)'; });
      r.addEventListener('mouseleave', function () { r.style.background = 'transparent'; });
      r.addEventListener('click', function (ev) { ev.preventDefault(); ev.stopPropagation(); closeMenu(); fn(); });
      menu.appendChild(r);
    }

    row('朗读选中内容', function () { speak(text, '选中内容'); });
    row('停止朗读', function () { stop(); });

    document.body.appendChild(menu);
    var rect = menu.getBoundingClientRect();
    menu.style.left = Math.max(4, Math.min(x, window.innerWidth - rect.width - 8)) + 'px';
    menu.style.top = Math.max(4, Math.min(y, window.innerHeight - rect.height - 8)) + 'px';
  }

  document.addEventListener('contextmenu', function (e) {
    var sel = '';
    try { sel = String(window.getSelection() || ''); } catch (err) {}
    if (sel.trim().length < 2) return;      // 没有选中文字：不接管，交给别的菜单
    var el = e.target;
    // 输入框内的选区交给 text-menu.js（那边有剪切/复制/粘贴）
    if (el && el.closest && el.closest('textarea,input,[contenteditable="true"]')) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    showSelectionMenu(e.clientX, e.clientY, sel.trim());
  }, true);

  document.addEventListener('mousedown', function (e) {
    var m = document.getElementById(MENU_ID);
    if (m && !m.contains(e.target)) closeMenu();
  }, true);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { stop(); closeMenu(); return; }
    if (e.ctrlKey && e.shiftKey && (e.key === 'R' || e.key === 'r')) {
      e.preventDefault();
      speakLastReply();
    }
  }, true);

  // 初始化
  function boot() {
    addChip();
    probe();
    try {
      if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = function () { probe(); };
    } catch (e) {}
  }
  if (document.body) boot(); else document.addEventListener('DOMContentLoaded', boot, { once: true });
})();
