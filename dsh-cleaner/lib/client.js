// dsh-cleaner — Client half (static / composition plugin)
//
// 两件事：
//  1. 设置里注册一个分区「清理与回收站」（和「手机端」同一个通道
//     slots.register('settings.section', …)）——工作区删除、已移除记录、回收站都在这儿；
//  2. 装饰产品自己的行 ⋯ 菜单：
//     · 会话行 → 追加「从列表移除」（红色垃圾桶图标，只解除关联、不动文件）
//     · 工作区行 → 接管原生「删除工作区」（原生的只摘登记、保留文件夹；
//       现在改为确认后把项目文件夹与会话记录一起搬进 DSH Recycle Bin）
window.__ModuleLoader__.load({
  id: 'dsh-cleaner',
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });
    let react = require('react');

    // ── plugin-owned JSON RPC over the host webServer route ──
    function rpc(method, args) {
      return fetch('/dsh-cleaner/api', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ method: method, args: args || {} }),
      }).then((r) => r.json()).catch((e) => ({ ok: false, reason: String(e && e.message !== undefined ? e.message : e) }));
    }

    function fmtBytes(n) {
      if (typeof n !== 'number' || !(n >= 0)) return '—';
      if (n < 1024) return n + ' B';
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
      return (n / 1024 / 1024).toFixed(1) + ' MB';
    }
    function fmtWhen(ms) {
      if (typeof ms !== 'number' || !(ms > 0)) return '';
      const d = new Date(ms);
      const pad = (x) => (x < 10 ? '0' + x : '' + x);
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    const inject = ['slots'];

    // ── 样式（只装一次） ──
    const STYLE_ID = 'dsh-cleaner-style';
    function installStyles() {
      if (document.getElementById(STYLE_ID)) return;
      const style = document.createElement('style');
      style.id = STYLE_ID;
      style.textContent = [
        '.dshcl-wrap{display:flex;flex-direction:column;gap:14px;padding:4px 2px 10px;color:var(--dsw-alias-label-primary);font-size:14px;line-height:22px}',
        '.dshcl-title{font-weight:600;font-size:15px}',
        '.dshcl-muted{color:var(--dsw-alias-label-secondary,#666);font-size:12.5px;line-height:1.7}',
        '.dshcl-card{border:1px solid var(--dsw-alias-border-l2,#00000014);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:8px}',
        '.dshcl-row{display:flex;align-items:center;gap:10px;min-width:0}',
        '.dshcl-name{min-width:0;flex:1;display:flex;flex-direction:column;gap:1px}',
        '.dshcl-name b{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
        '.dshcl-sub{font-size:11.5px;opacity:.65;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
        '.dshcl-btn{padding:3px 10px;border-radius:7px;border:1px solid var(--dsw-alias-border-l2,#0000001f);background:transparent;color:inherit;font:inherit;font-size:12.5px;cursor:pointer;white-space:nowrap}',
        '.dshcl-btn:disabled{opacity:.5;cursor:default}',
        '.dshcl-btn-danger{color:var(--dsw-alias-state-error-primary,#d92d20)}',
        '.dshcl-head{display:flex;align-items:center;gap:10px}',
        '.dshcl-head .dshcl-title{flex:1}',
        '.dshcl-empty{font-size:12.5px;opacity:.6}',
      ].join('\n');
      document.head.appendChild(style);
    }

    // ── 面内确认框（不依赖 window.confirm） ──
    function confirmBox(title, detail, okLabel, onOk) {
      const box = document.createElement('div');
      box.setAttribute('data-dsh-confirm', '1');
      box.style.cssText = 'position:fixed;inset:0;z-index:2147483001;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.35);';
      const card = document.createElement('div');
      card.style.cssText = 'width:min(460px,calc(100vw - 32px));padding:16px 18px;border-radius:12px;' +
        'background:var(--dsw-alias-bg-layer-1,#fff);color:var(--dsw-alias-label-primary,#222);' +
        'border:1px solid var(--dsw-alias-border-l2,rgba(128,128,128,0.35));box-shadow:0 16px 40px rgba(0,0,0,0.25);' +
        'font:13px/1.7 var(--dsh-font-family,inherit);';
      const h = document.createElement('div');
      h.textContent = title;
      h.style.cssText = 'font-weight:600;margin-bottom:6px;';
      const d = document.createElement('div');
      d.textContent = detail;
      d.style.cssText = 'opacity:0.8;white-space:pre-wrap;margin-bottom:14px;';
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;';
      const cancel = document.createElement('button');
      cancel.textContent = '取消';
      const ok = document.createElement('button');
      ok.textContent = okLabel || '确定';
      for (const [b, danger] of [[cancel, false], [ok, true]]) {
        b.style.cssText = 'padding:5px 14px;border-radius:8px;border:1px solid var(--dsw-alias-border-l2,rgba(128,128,128,0.35));' +
          'background:transparent;color:' + (danger ? 'var(--dsw-alias-state-error-primary,#d92d20)' : 'inherit') + ';font:inherit;cursor:pointer;';
      }
      const close = () => box.remove();
      cancel.addEventListener('click', close);
      ok.addEventListener('click', () => { close(); onOk(); });
      box.addEventListener('click', (e) => { if (e.target === box) close(); });
      row.append(cancel, ok);
      card.append(h, d, row);
      box.append(card);
      document.body.appendChild(box);
    }

    function alertBox(text) {
      confirmBox('清理与回收站', text, '知道了', () => { });
    }

    // ── 设置分区：清理与回收站 ──
    function CleanerSection() {
      const [data, setData] = react.useState(null);
      const [error, setError] = react.useState(null);
      const [busy, setBusy] = react.useState('');
      const [nonce, setNonce] = react.useState(0);

      react.useEffect(() => {
        let alive = true;
        setError(null);
        Promise.all([rpc('list', {}), rpc('recycle-list', {})]).then(([l, b]) => {
          if (!alive) return;
          if (!l || l.ok !== true) { setError((l && l.reason) || '读取失败'); setData(null); return; }
          setData({
            workspaces: l.workspaces || [],
            orphans: l.orphans || [],
            detached: l.detached || [],
            bin: (b && b.entries) || [],
            binPath: (b && b.bin) || l.recycleBin || '',
          });
        });
        return () => { alive = false; };
      }, [nonce]);

      const run = (key, method, args, done) => {
        setBusy(key);
        rpc(method, args).then((res) => {
          setBusy('');
          if (res && res.ok) { if (done) done(res); else setNonce((n) => n + 1); return; }
          alertBox('操作失败：' + ((res && res.reason) || '未知错误'));
        });
      };

      const delWorkspace = (ws) => {
        confirmBox(
          '删除工作区「' + (ws.title || ws.path) + '」',
          '将把整个项目文件夹（含里面所有文件，原样不改）连同它的会话记录一起移入：\n' +
          (data.binPath || 'C:\\Users\\<你>\\Documents\\DSH Recycle Bin') + '\n\n' +
          '回收条目里会写好「恢复说明.md」与「恢复.ps1」，随时可以还原。',
          '移入回收站',
          () => run('ws:' + ws.id, 'delete-workspace', { workspaceId: ws.id }, (res) => {
            setNonce((n) => n + 1);
            alertBox('已移入回收站：\n' + (res.recycleEntry || '') + '\n' + (res.recycleBin || ''));
          }),
        );
      };

      const children = [];
      children.push(react.createElement('div', { key: 'head', className: 'dshcl-head' }, [
        react.createElement('div', { key: 't', className: 'dshcl-title' }, '清理与回收站'),
        react.createElement('button', {
          key: 'r', type: 'button', className: 'dshcl-btn',
          onClick: () => setNonce((n) => n + 1), disabled: busy !== '',
        }, '刷新'),
      ]));
      children.push(react.createElement('div', { key: 'note', className: 'dshcl-muted' },
        '删除工作区 = 把整个项目文件夹与会话记录搬进 DSH Recycle Bin（可还原）；删除会话请在会话行右侧的 ⋯ 菜单里选「从列表移除」——那一步只解除关联，磁盘上的文件一个都不动。'));

      if (error) children.push(react.createElement('div', { key: 'err', className: 'dshcl-muted' }, '读取失败：' + error));
      else if (data === null) children.push(react.createElement('div', { key: 'loading', className: 'dshcl-muted' }, '读取中…'));
      else {
        const totalBytes = data.workspaces.reduce((s, w) => s + (w.bytes || 0), 0);
        const totalSessions = data.workspaces.reduce((s, w) => s + w.sessions.length, 0);
        children.push(react.createElement('div', { key: 'sum', className: 'dshcl-muted' },
          `${data.workspaces.length} 个工作区 · ${totalSessions} 个会话 · 会话记录共 ${fmtBytes(totalBytes)}` +
          (data.detached.length ? ` · 已移除 ${data.detached.length} 个（记录保留）` : '') +
          (data.orphans.length ? ` · 孤儿 ${data.orphans.length} 个` : '')));

        // 工作区
        for (const ws of data.workspaces) {
          const rows = [
            react.createElement('div', { key: 'r', className: 'dshcl-row' }, [
              react.createElement('div', { key: 'n', className: 'dshcl-name' }, [
                react.createElement('b', { key: 't' }, ws.title || '(未命名工作区)'),
                react.createElement('span', { key: 's', className: 'dshcl-sub' },
                  `${ws.sessions.length} 个会话 · 记录 ${fmtBytes(ws.bytes)}` +
                  (typeof ws.projectBytes === 'number' ? ` · 项目 ${fmtBytes(ws.projectBytes)}` : '') +
                  ` · ${ws.path || ''}`),
              ]),
              react.createElement('button', {
                key: 'd', type: 'button', className: 'dshcl-btn dshcl-btn-danger',
                disabled: busy === 'ws:' + ws.id,
                onClick: () => delWorkspace(ws),
              }, busy === 'ws:' + ws.id ? '搬运中…' : '删除工作区（含项目）'),
            ]),
          ];
          for (const s of ws.sessions) {
            const tags = [];
            if (s.open) tags.push('使用中');
            if (s.archived) tags.push('已归档');
            rows.push(react.createElement('div', { key: 's' + s.id, className: 'dshcl-row', style: { paddingLeft: 14 } }, [
              react.createElement('div', { key: 'n', className: 'dshcl-name' }, [
                react.createElement('span', { key: 't' }, s.title || s.id),
                react.createElement('span', { key: 's', className: 'dshcl-sub' },
                  [fmtBytes(s.bytes), s.turns !== null ? s.turns + ' 轮' : null, s.mtime ? fmtWhen(s.mtime) : null]
                    .filter(Boolean).join(' · ') + (tags.length ? ' · ' + tags.join('/') : '')),
              ]),
              react.createElement('span', { key: 'h', className: 'dshcl-sub', title: '删除会话请用会话行右侧的 ⋯ 菜单' }, '⋯'),
            ]));
          }
          children.push(react.createElement('div', { key: 'ws' + ws.id, className: 'dshcl-card' }, rows));
        }

        // 已从列表移除（记录仍保留）
        if (data.detached.length > 0) {
          const rows = [react.createElement('div', { key: 'h', className: 'dshcl-muted' }, '已从列表移除（记录仍原样保留在磁盘上，dsh 不再显示）')];
          for (const d of data.detached) {
            rows.push(react.createElement('div', { key: d.id, className: 'dshcl-row' }, [
              react.createElement('div', { key: 'n', className: 'dshcl-name' }, [
                react.createElement('span', { key: 't' }, d.title || d.id),
                react.createElement('span', { key: 's', className: 'dshcl-sub' },
                  [fmtBytes(d.bytes), d.mtime ? fmtWhen(d.mtime) : null].filter(Boolean).join(' · ')),
              ]),
              react.createElement('button', {
                key: 'back', type: 'button', className: 'dshcl-btn', disabled: busy === 'back:' + d.id,
                onClick: () => run('back:' + d.id, 'attach-session', { sessionId: d.id }),
              }, busy === 'back:' + d.id ? '加入中…' : '重新加入列表'),
              react.createElement('button', {
                key: 'bin', type: 'button', className: 'dshcl-btn dshcl-btn-danger', disabled: busy === 'bin:' + d.id,
                onClick: () => confirmBox('移入回收站', '把这条会话记录搬到 DSH Recycle Bin？\n' + (d.title || d.id) + '\n\n记录会原样保留，可随时还原。', '移入回收站',
                  () => run('bin:' + d.id, 'delete-orphan', { sessionId: d.id })),
              }, '移入回收站'),
            ]));
          }
          children.push(react.createElement('div', { key: 'detached', className: 'dshcl-card' }, rows));
        }

        // 孤儿
        if (data.orphans.length > 0) {
          const CAP = 20;
          const rows = [react.createElement('div', { key: 'h', className: 'dshcl-muted' }, '孤儿会话（不在任何工作区登记里，多为接口任务残留）')];
          for (const o of data.orphans.slice(0, CAP)) {
            rows.push(react.createElement('div', { key: o.id, className: 'dshcl-row' }, [
              react.createElement('div', { key: 'n', className: 'dshcl-name' }, [
                react.createElement('span', { key: 't' }, o.id),
                react.createElement('span', { key: 's', className: 'dshcl-sub' },
                  [fmtBytes(o.bytes), o.mtime ? fmtWhen(o.mtime) : null].filter(Boolean).join(' · ')),
              ]),
              react.createElement('button', {
                key: 'bin', type: 'button', className: 'dshcl-btn', disabled: busy === 'or:' + o.id,
                onClick: () => confirmBox('移入回收站', '把这个孤儿会话记录搬到 DSH Recycle Bin？\n' + o.id, '移入回收站',
                  () => run('or:' + o.id, 'delete-orphan', { sessionId: o.id })),
              }, '移入回收站'),
            ]));
          }
          if (data.orphans.length > CAP) {
            rows.push(react.createElement('div', { key: 'more', className: 'dshcl-muted' },
              `…… 还有 ${data.orphans.length - CAP} 个孤儿记录未列出（共 ${data.orphans.length} 个）`));
          }
          children.push(react.createElement('div', { key: 'orphans', className: 'dshcl-card' }, rows));
        }

        // 回收站
        const binRows = [react.createElement('div', { key: 'h', className: 'dshcl-muted' },
          'DSH Recycle Bin' + (data.binPath ? '：' + data.binPath : '') + (data.bin.length ? `（${data.bin.length} 条，可还原）` : '（空）'))];
        const KIND = { workspace: '工作区（含项目文件夹）', session: '会话记录', orphan: '孤儿记录' };
        for (const t of data.bin) {
          binRows.push(react.createElement('div', { key: t.name, className: 'dshcl-row' }, [
            react.createElement('div', { key: 'n', className: 'dshcl-name' }, [
              react.createElement('span', { key: 't' }, `${KIND[t.kind] || '回收条目'} · ${t.title || t.sessionId}`),
              react.createElement('span', { key: 's', className: 'dshcl-sub' },
                [fmtBytes(t.bytes), t.when ? t.when.slice(0, 19).replace('T', ' ') : null, t.projectPath || null]
                  .filter(Boolean).join(' · ')),
            ]),
            react.createElement('button', {
              key: 'r', type: 'button', className: 'dshcl-btn', disabled: busy === 'rs:' + t.name,
              onClick: () => run('rs:' + t.name, 'restore', { name: t.name }),
            }, busy === 'rs:' + t.name ? '还原中…' : (t.kind === 'workspace' ? '还原项目' : '恢复')),
          ]));
        }
        children.push(react.createElement('div', { key: 'bin', className: 'dshcl-card' }, binRows));
      }

      return react.createElement('div', { className: 'dshcl-wrap' }, children);
    }

    // ── 行 ⋯ 菜单装饰器 ──
    // 菜单是挂在 body 上的 portal，与行没有 DOM 连接；身份线索 = ⋯ 按钮的
    // aria-label（会话“<标题>”的操作 / 工作区“<标题>”的操作）。
    // 垃圾桶图形（行菜单与设置导航共用同一份，保证「之前那个垃圾桶」处处一致）
    const TRASH_GLYPH = '<g fill="none">' +
      '<path d="M2.6 4.4h10.8M6.2 4.4V3.2c0-.5.4-.9.9-.9h1.8c.5 0 .9.4.9.9v1.2M4.1 4.4l.5 8.2c0 .6.5 1.1 1.1 1.1h4.6c.6 0 1.1-.5 1.1-1.1l.5-8.2" ' +
      'stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<path d="M6.6 6.9v4.1M9.4 6.9v4.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></g>';
    const TRASH_SVG = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      TRASH_GLYPH + '</svg>';
    const DANGER = 'var(--dsw-alias-state-error-primary,#d92d20)';
    const SESSION_TRIGGER_RE = /^会话[“"](.+?)[”"]的操作$/;
    const WORKSPACE_TRIGGER_RE = /^工作区[“"](.+?)[”"]的操作$/;
    let lastSessionTrigger = null;
    let lastWorkspaceTrigger = null;
    let lastBinPath = '';

    function rememberTrigger(ev) {
      const t = ev.target;
      if (!t || typeof t.closest !== 'function') return;
      const btn = t.closest('button[aria-label]');
      if (!btn) return;
      const label = btn.getAttribute('aria-label') || '';
      let m = SESSION_TRIGGER_RE.exec(label);
      if (m) {
        const row = btn.closest('[role="treeitem"]');
        const group = row && typeof row.closest === 'function' ? row.closest('div[class*="groupSection"]') : null;
        lastSessionTrigger = { title: m[1].trim(), workspaceTitle: group ? String(group.innerText || '').split('\n')[0].trim() : '', at: Date.now() };
        return;
      }
      m = WORKSPACE_TRIGGER_RE.exec(label);
      if (m) lastWorkspaceTrigger = { title: m[1].trim(), at: Date.now() };
    }

    function closeMenus() {
      try {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
      } catch (e) { /* ignore */ }
    }

    /** 克隆产品自己的菜单条目做模板；红色只写在图标层（产品给图标 span 设了自己的 color）。 */
    function makeItem(templateBtn, label, opts) {
      const wrap = templateBtn.parentElement.cloneNode(true);
      const btn = wrap.querySelector('button[role="menuitem"]') || wrap;
      btn.removeAttribute('style');
      if (!(opts && opts.danger)) {
        for (const el of [wrap, btn]) {
          const cls = String(el.className || '');
          if (/danger/i.test(cls)) el.className = cls.split(/\s+/).filter((c) => !/danger/i.test(c)).join(' ');
        }
      }
      const labelEl = btn.querySelector('span[class*="itemLabel"]') || btn;
      labelEl.textContent = label;
      labelEl.style.color = '';
      const iconEl = btn.querySelector('span[class*="itemIcon"]');
      if (iconEl) {
        iconEl.innerHTML = TRASH_SVG;
        iconEl.style.color = (opts && opts.iconColor) ? opts.iconColor : '';
      }
      if (opts && opts.onClick) btn.addEventListener('click', opts.onClick, true);
      return wrap;
    }

    function decorateMenus() {
      for (const menu of document.querySelectorAll('[role="menu"]')) {
        if (menu.getAttribute('data-dsh-cleaner') === '1') continue;
        const items = [...menu.querySelectorAll('button[role="menuitem"]')];
        if (items.length === 0) continue;
        const labels = items.map((b) => (b.innerText || '').trim());
        const isSessionMenu = labels.includes('重命名') && labels.some((l) => /分叉|归档/.test(l));
        const isWorkspaceMenu = labels.includes('重命名') && labels.includes('删除工作区');
        if (!isSessionMenu && !isWorkspaceMenu) continue;
        menu.setAttribute('data-dsh-cleaner', '1');

        if (isSessionMenu) {
          const template = items[items.length - 1];
          const wrap = makeItem(template, '从列表移除', {
            iconColor: DANGER,
            onClick: (ev) => {
              ev.preventDefault(); ev.stopPropagation();
              const who = lastSessionTrigger && Date.now() - lastSessionTrigger.at < 120000 ? lastSessionTrigger : null;
              if (!who) { alertBox('无法确定是哪个会话：请重新点开该会话行的 ⋯ 菜单。'); return; }
              closeMenus();
              rpc('detach-title', { title: who.title, workspaceTitle: who.workspaceTitle }).then((res) => {
                if (res && res.ok) return;
                alertBox('移除失败：' + ((res && res.reason) || '未知错误'));
              });
            },
          });
          template.parentElement.parentElement.appendChild(wrap);
        }

        if (isWorkspaceMenu) {
          const native = items.find((b) => (b.innerText || '').trim() === '删除工作区');
          if (native && native.getAttribute('data-dsh-cleaner-hooked') !== '1') {
            native.setAttribute('data-dsh-cleaner-hooked', '1');
            native.addEventListener('click', (ev) => {
              ev.preventDefault(); ev.stopPropagation();
              const who = lastWorkspaceTrigger && Date.now() - lastWorkspaceTrigger.at < 120000 ? lastWorkspaceTrigger : null;
              if (!who) { alertBox('无法确定是哪个工作区：请重新点开该工作区行的 ⋯ 菜单。'); return; }
              closeMenus();
              confirmBox(
                '删除工作区「' + who.title + '」',
                '将把整个项目文件夹（含里面所有文件，原样不改）连同它的会话记录一起移入：\n' +
                (lastBinPath || 'C:\\Users\\<你>\\Documents\\DSH Recycle Bin') + '\n\n' +
                '回收条目里会写好「恢复说明.md」与「恢复.ps1」，随时可以还原。',
                '移入回收站',
                () => {
                  rpc('delete-workspace-by-title', { title: who.title }).then((res) => {
                    if (res && res.ok) { alertBox('已移入回收站：\n' + (res.recycleEntry || '')); return; }
                    alertBox('删除失败：' + ((res && res.reason) || '未知错误'));
                  });
                },
              );
            }, true);
          }
        }
      }
    }

    // ── 设置导航里「清理与回收站」那一行的图标 ──
    // DSH 的导航图标按分区 id 硬编码（只有 models / agent-presets / plugins 有专属图形，
    // 其余一律齿轮），而 slots.register 只收 id/order/label，给不了自定义图标。
    // 所以在页面里把这一行的 svg 内容换成垃圾桶：stroke 走 currentColor，
    // 深浅色主题、选中/未选中态都自动跟随文字颜色（与相邻图标观感一致）。
    const NAV_LABEL = '清理与回收站';
    function markCleanerNavIcon() {
      const icons = document.querySelectorAll('svg[class*="navIcon"]');
      for (const svg of icons) {
        if (svg.getAttribute('data-dshcl-navicon') === '1') continue;
        let holder = svg.parentElement;
        let text = '';
        for (let i = 0; i < 3 && holder; i++) {
          text = String(holder.textContent || '').trim();
          if (text) break;
          holder = holder.parentElement;
        }
        if (text !== NAV_LABEL) continue;
        svg.setAttribute('data-dshcl-navicon', '1');
        svg.setAttribute('viewBox', '0 0 16 16');
        svg.setAttribute('fill', 'none');
        svg.innerHTML = TRASH_GLYPH;
      }
    }

    let menuObserver = null;
    function installDecorators(ctx) {
      document.addEventListener('pointerdown', rememberTrigger, true);
      document.addEventListener('click', rememberTrigger, true);
      menuObserver = new MutationObserver(() => { decorateMenus(); markCleanerNavIcon(); });
      menuObserver.observe(document.body, { childList: true, subtree: true });
      const timer = setInterval(() => { decorateMenus(); markCleanerNavIcon(); }, 800);
      ctx.effect(() => () => {
        document.removeEventListener('pointerdown', rememberTrigger, true);
        document.removeEventListener('click', rememberTrigger, true);
        if (menuObserver) menuObserver.disconnect();
        clearInterval(timer);
      });
    }

    // ── plugin body ──
    function apply(ctx) {
      installStyles();
      installDecorators(ctx);
      markCleanerNavIcon();
      rpc('list', {}).then((r) => { if (r && r.ok && r.recycleBin) lastBinPath = r.recycleBin; });
      const slots = ctx.get('slots');
      if (slots === undefined) return;
      slots.inject('settings.section', () => slots.register(
        { name: 'settings.section', id: 'cleaner', order: 45, label: () => '清理与回收站' },
        () => CleanerSection(),
      ));
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  }
});
