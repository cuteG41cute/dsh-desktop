// dsh-cleaner — Client half (static / composition plugin)
//
// Browser bundle consumed by the client module loader (window.__ModuleLoader__).
// Talks to the Host through the plugin's own JSON API on the webServer route
// (POST /dsh-cleaner/api) via fetch. Adds a 「清理」 chip to the conversation
// header; the chip opens a management panel listing every workspace with its
// sessions (title / size / turns / last activity) plus orphan sessions and a
// restorable trash. Deletions are two-step confirmed and move files into the
// host-side trash, so the product sidebar updates itself via the registry feed.
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

    const inject = [];

    const chipStyle = {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '3px 10px',
      borderRadius: 999,
      border: '1px solid var(--dsw-alias-divider, rgba(128,128,128,0.35))',
      background: 'transparent',
      color: 'var(--dsw-alias-label-secondary, #8a8a8a)',
      fontSize: 12,
      lineHeight: '18px',
      cursor: 'pointer',
      fontFamily: 'inherit',
      whiteSpace: 'nowrap',
    };

    // ── formatting helpers ──
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

    // ── panel (plain DOM overlay; data comes from the host API) ──
    const PANEL_ID = 'dsh-cleaner-panel';

    function closePanel() {
      const el = document.getElementById(PANEL_ID);
      if (el) el.remove();
    }
    function togglePanel() {
      if (document.getElementById(PANEL_ID)) { closePanel(); return; }
      const overlay = document.createElement('div');
      overlay.id = PANEL_ID;
      Object.assign(overlay.style, {
        position: 'fixed', top: '44px', right: '12px',
        width: 'min(460px, calc(100vw - 16px))',
        maxHeight: 'min(75vh, 720px)', overflow: 'auto',
        zIndex: 2147483000, padding: '12px', borderRadius: '12px',
        background: 'var(--dsw-alias-surface-primary, #fff)',
        color: 'var(--dsw-alias-label-primary, #222)',
        border: '1px solid var(--dsw-alias-divider, rgba(128,128,128,0.35))',
        boxShadow: '0 12px 32px rgba(0,0,0,0.18)',
        font: '13px/1.6 var(--dsh-font-family, inherit)',
      });
      document.body.appendChild(overlay);
      refreshPanel();
    }

    function panelNote(text, tone) {
      const div = document.createElement('div');
      div.textContent = text;
      div.style.cssText = 'margin:6px 0;font-size:12px;opacity:0.75;' +
        (tone === 'error' ? 'color:var(--dsw-alias-state-error-primary,#d92d20);opacity:1;' : '');
      return div;
    }

    /** 两步确认按钮：第一下变「确认…？」，3 秒内再点才执行。 */
    function dangerButton(label, onConfirm, armedLabel, busyLabel) {
      const btn = document.createElement('button');
      btn.textContent = label;
      btn.style.cssText = 'padding:2px 8px;border-radius:6px;border:1px solid var(--dsw-alias-divider,rgba(128,128,128,0.35));' +
        'background:transparent;color:inherit;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap;';
      let armed = false;
      let timer = 0;
      btn.addEventListener('click', () => {
        if (!armed) {
          armed = true;
          btn.textContent = armedLabel || '确认删除？';
          btn.style.color = 'var(--dsw-alias-state-error-primary,#d92d20)';
          btn.style.borderColor = 'var(--dsw-alias-state-error-primary,#d92d20)';
          clearTimeout(timer);
          timer = setTimeout(() => {
            armed = false;
            btn.textContent = label;
            btn.style.color = '';
            btn.style.borderColor = '';
          }, 3000);
          return;
        }
        clearTimeout(timer);
        btn.disabled = true;
        btn.textContent = busyLabel || '删除中…';
        onConfirm().finally(() => { btn.disabled = false; });
      });
      return btn;
    }

    function rowLabel(main, sub) {
      const wrap = document.createElement('div');
      wrap.style.cssText = 'min-width:0;display:flex;flex-direction:column;gap:1px;flex:1;';
      const a = document.createElement('div');
      a.textContent = main;
      a.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
      const b = document.createElement('div');
      b.textContent = sub;
      b.style.cssText = 'font-size:11px;opacity:0.65;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
      wrap.append(a, b);
      return wrap;
    }

    function sectionTitle(text) {
      const div = document.createElement('div');
      div.textContent = text;
      div.style.cssText = 'margin:10px 0 4px;font-weight:600;font-size:12px;opacity:0.8;';
      return div;
    }

    function refreshPanel() {
      const overlay = document.getElementById(PANEL_ID);
      if (!overlay) return;
      overlay.textContent = '';
      const head = document.createElement('div');
      head.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:4px;';
      const title = document.createElement('div');
      title.textContent = '清理 · 会话与工作区';
      title.style.cssText = 'font-weight:600;flex:1;';
      const refresh = document.createElement('button');
      refresh.textContent = '刷新';
      refresh.style.cssText = chipStyle;
      refresh.addEventListener('click', refreshPanel);
      const close = document.createElement('button');
      close.textContent = '×';
      close.style.cssText = chipStyle + 'min-width:24px;justify-content:center;';
      close.addEventListener('click', closePanel);
      head.append(title, refresh, close);
      overlay.append(head);
      overlay.append(panelNote('删除工作区 = 把整个项目文件夹（含全部文件，原样未改）连同它的会话记录一起搬进 DSH Recycle Bin，并写好恢复说明与恢复脚本。删除会话 = 只解除它与 dsh 的关联（会话列表里消失），磁盘上任何文件都不动。正在打开的会话会被拒绝。', null));

      const busy = document.createElement('div');
      busy.textContent = '读取中…';
      busy.style.cssText = 'font-size:12px;opacity:0.7;';
      overlay.append(busy);

      let trashEntries = [];
      rpc('recycle-list', {}).then((r) => { if (r && r.ok) { trashEntries = r.entries || []; if (r.bin) cachedBin = r.bin; } });

      rpc('list', {}).then((r) => {
        if (!overlay.isConnected) return;
        busy.remove();
        if (!r || r.ok !== true) {
          overlay.append(panelNote('读取失败：' + ((r && r.reason) || '未知错误'), 'error'));
          return;
        }
        const workspaces = r.workspaces || [];
        const orphans = r.orphans || [];
        const detached = r.detached || [];
        const totalBytes = workspaces.reduce((s, w) => s + (w.bytes || 0), 0);
        const totalSessions = workspaces.reduce((s, w) => s + w.sessions.length, 0);
        overlay.append(panelNote(`${workspaces.length} 个工作区 · ${totalSessions} 个会话 · 共 ${fmtBytes(totalBytes)}` +
          (detached.length ? ` · 已移除 ${detached.length} 个（记录保留）` : '') +
          (orphans.length ? ` · 孤儿 ${orphans.length} 个` : ''), null));

        for (const ws of workspaces) {
          const group = document.createElement('div');
          group.style.cssText = 'border-top:1px solid var(--dsw-alias-divider,rgba(128,128,128,0.25));padding:6px 0 2px;';
          const head = document.createElement('div');
          head.style.cssText = 'display:flex;align-items:center;gap:8px;';
          head.append(rowLabel(
            ws.title || '(未命名工作区)',
            `${ws.sessions.length} 个会话 · 记录 ${fmtBytes(ws.bytes)}` +
            (typeof ws.projectBytes === 'number' ? ` · 项目 ${fmtBytes(ws.projectBytes)}` : '') +
            ` · ${ws.path || ''}`,
          ));
          if (ws.sessions.length > 0 || true) {
            head.append(dangerButton('删除工作区（含项目）', () => {
              return rpc('delete-workspace', { workspaceId: ws.id }).then((res) => {
                if (res && res.ok) {
                  alert('已搬入回收站：\n' + (res.recycleEntry || '') + '\n' + (res.recycleBin || '') +
                    '\n\n项目文件夹与会话记录原样保留，可按里面的「恢复说明.md」还原。');
                  refreshPanel();
                  return;
                }
                alert('删除失败：' + ((res && res.reason) || '未知错误'));
                refreshPanel();
              });
            }));
          }
          group.append(head);
          for (const s of ws.sessions) {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:3px 0 3px 14px;';
            const tags = [];
            if (s.open) tags.push('使用中');
            if (s.archived) tags.push('已归档');
            const sub = [fmtBytes(s.bytes), s.turns !== null ? s.turns + ' 轮' : null,
              s.mtime ? fmtWhen(s.mtime) : null].filter(Boolean).join(' · ');
            row.append(rowLabel(
              s.title || s.id,
              sub + (tags.length ? ' · ' + tags.join('/') : ''),
            ));
            if (s.open) {
              const tag = document.createElement('span');
              tag.textContent = '使用中';
              tag.style.cssText = 'font-size:11px;opacity:0.6;white-space:nowrap;';
              row.append(tag);
            } else {
              const hint = document.createElement('span');
              hint.textContent = '⋯';
              hint.title = '删除会话请用会话行右侧的 ⋯ 菜单（重命名 / 分叉会话 / 归档会话 旁边）';
              hint.style.cssText = 'font-size:12px;opacity:0.45;white-space:nowrap;';
              row.append(hint);
            }
            group.append(row);
          }
          overlay.append(group);
        }

        if (detached.length > 0) {
          overlay.append(sectionTitle('已从列表移除（记录仍原样保留在磁盘上，dsh 不再显示）'));
          for (const d of detached) {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:3px 0;';
            row.append(rowLabel(
              d.title || d.id,
              [fmtBytes(d.bytes), d.mtime ? fmtWhen(d.mtime) : null].filter(Boolean).join(' · '),
            ));
            if (!d.open) {
              const back = document.createElement('button');
              back.textContent = '重新加入列表';
              back.style.cssText = 'padding:2px 8px;border-radius:6px;border:1px solid var(--dsw-alias-divider,rgba(128,128,128,0.35));background:transparent;color:inherit;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap;';
              back.addEventListener('click', () => {
                back.disabled = true;
                rpc('attach-session', { sessionId: d.id }).then((res) => {
                  if (res && res.ok) { refreshPanel(); return; }
                  alert('重新加入失败：' + ((res && res.reason) || '未知错误'));
                  back.disabled = false;
                });
              });
              row.append(back);
              row.append(dangerButton('移入回收站', () => {
                return rpc('delete-orphan', { sessionId: d.id }).then((res) => {
                  if (res && res.ok) { refreshPanel(); return; }
                  alert('操作失败：' + ((res && res.reason) || '未知错误'));
                  refreshPanel();
                });
              }, '确认移入？', '搬运中…'));
            }
            overlay.append(row);
          }
        }

        if (orphans.length > 0) {
          overlay.append(sectionTitle('孤儿会话（不在任何工作区登记里，多为接口任务残留）'));
          for (const o of orphans) {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:3px 0;';
            row.append(rowLabel(o.id, [fmtBytes(o.bytes), o.mtime ? fmtWhen(o.mtime) : null].filter(Boolean).join(' · ')));
            if (!o.open) {
              row.append(dangerButton('移入回收站', () => {
                return rpc('delete-orphan', { sessionId: o.id }).then((res) => {
                  if (res && res.ok) { refreshPanel(); return; }
                  alert('操作失败：' + ((res && res.reason) || '未知错误'));
                  refreshPanel();
                });
              }, '确认移入？', '搬运中…'));
            }
            overlay.append(row);
          }
        }

        if (trashEntries.length > 0) {
          const details = document.createElement('details');
          details.style.cssText = 'margin-top:10px;';
          const summary = document.createElement('summary');
          summary.textContent = `DSH Recycle Bin（${trashEntries.length} 条，可还原）`;
          summary.style.cssText = 'cursor:pointer;font-size:12px;opacity:0.8;';
          details.append(summary);
          const KIND_LABEL = { workspace: '工作区（含项目文件夹）', session: '会话记录', orphan: '孤儿会话记录' };
          for (const t of trashEntries) {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:3px 0;';
            const kind = KIND_LABEL[t.kind] || '回收条目';
            row.append(rowLabel(
              `${kind} · ${t.title || t.sessionId}`,
              [fmtBytes(t.bytes), t.when ? t.when.slice(0, 19).replace('T', ' ') : null,
                t.projectPath || null].filter(Boolean).join(' · '),
            ));
            const btn = document.createElement('button');
            btn.textContent = t.kind === 'workspace' ? '还原项目' : '恢复';
            btn.style.cssText = 'padding:2px 8px;border-radius:6px;border:1px solid var(--dsw-alias-divider,rgba(128,128,128,0.35));background:transparent;color:inherit;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap;';
            btn.addEventListener('click', () => {
              btn.disabled = true;
              rpc('restore', { name: t.name }).then((res) => {
                if (res && res.ok) { refreshPanel(); return; }
                alert('恢复失败：' + ((res && res.reason) || '未知错误'));
                btn.disabled = false;
              });
            });
            row.append(btn);
            details.append(row);
          }
          overlay.append(details);
        }
      }).catch((e) => {
        busy.remove();
        overlay.append(panelNote('读取异常：' + String(e && e.message !== undefined ? e.message : e), 'error'));
      });
    }

    // ── 行 ⋯ 菜单装饰器 ──
    // 菜单是挂在 body 上的 portal，与行没有 DOM 连接；身份线索 = ⋯ 按钮的
    // aria-label（会话“<标题>”的操作 / 工作区“<标题>”的操作）。
    const TRASH_SVG = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M2.6 4.4h10.8M6.2 4.4V3.2c0-.5.4-.9.9-.9h1.8c.5 0 .9.4.9.9v1.2M4.1 4.4l.5 8.2c0 .6.5 1.1 1.1 1.1h4.6c.6 0 1.1-.5 1.1-1.1l.5-8.2" ' +
      'stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<path d="M6.6 6.9v4.1M9.4 6.9v4.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>';
    const DANGER = 'var(--dsw-alias-state-error-primary,#d92d20)';
    let cachedBin = '';
    const SESSION_TRIGGER_RE = /^会话[“"](.+?)[”"]的操作$/;
    const WORKSPACE_TRIGGER_RE = /^工作区[“"](.+?)[”"]的操作$/;
    let lastSessionTrigger = null;
    let lastWorkspaceTrigger = null;

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
        const groupTitle = group ? String(group.innerText || '').split('\n')[0].trim() : '';
        lastSessionTrigger = { title: m[1].trim(), workspaceTitle: groupTitle, at: Date.now() };
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

    /** 用产品自己的菜单条目做模板，克隆出一个同款条目（含 danger 红色与垃圾桶图标）。 */
    function makeItem(templateBtn, label, opts) {
      const wrap = templateBtn.parentElement.cloneNode(true);
      const btn = wrap.querySelector('button[role="menuitem"]') || wrap;
      const labelEl = btn.querySelector('span[class*="itemLabel"]') || btn;
      labelEl.textContent = label;
      const iconEl = btn.querySelector('span[class*="itemIcon"]');
      if (iconEl) iconEl.innerHTML = TRASH_SVG;
      btn.style.color = DANGER;
      if (opts && opts.onClick) btn.addEventListener('click', opts.onClick, true);
      return wrap;
    }

    /** 面内确认框（不依赖 window.confirm，WebView 里更稳）。 */
    function confirmBox(title, detail, okLabel, onOk) {
      const box = document.createElement('div');
      box.style.cssText = 'position:fixed;inset:0;z-index:2147483001;display:flex;align-items:center;justify-content:center;' +
        'background:rgba(0,0,0,0.35);';
      const card = document.createElement('div');
      card.style.cssText = 'width:min(460px,calc(100vw - 32px));padding:16px 18px;border-radius:12px;' +
        'background:var(--dsw-alias-surface-primary,#fff);color:var(--dsw-alias-label-primary,#222);' +
        'border:1px solid var(--dsw-alias-divider,rgba(128,128,128,0.35));box-shadow:0 16px 40px rgba(0,0,0,0.25);' +
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
        b.style.cssText = 'padding:5px 14px;border-radius:8px;border:1px solid var(--dsw-alias-divider,rgba(128,128,128,0.35));' +
          'background:transparent;color:' + (danger ? DANGER : 'inherit') + ';font:inherit;cursor:pointer;';
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

    function decorateMenus() {
      const menus = document.querySelectorAll('[role="menu"]');
      for (const menu of menus) {
        if (menu.getAttribute('data-dsh-cleaner') === '1') continue;
        const items = [...menu.querySelectorAll('button[role="menuitem"]')];
        if (items.length === 0) continue;
        const labels = items.map((b) => (b.innerText || '').trim());
        const isSessionMenu = labels.includes('重命名') && labels.some((l) => /分叉|归档/.test(l));
        const isWorkspaceMenu = labels.includes('重命名') && labels.includes('删除工作区');
        if (!isSessionMenu && !isWorkspaceMenu) continue;
        menu.setAttribute('data-dsh-cleaner', '1');

        if (isSessionMenu && !labels.includes('从列表移除')) {
          const template = items[items.length - 1];
          const wrap = makeItem(template, '从列表移除', {
            onClick: (ev) => {
              ev.preventDefault(); ev.stopPropagation();
              const who = lastSessionTrigger && Date.now() - lastSessionTrigger.at < 120000 ? lastSessionTrigger : null;
              if (!who) { alert('无法确定是哪个会话：请重新点开该会话行的 ⋯ 菜单。'); return; }
              closeMenus();
              rpc('detach-title', { title: who.title, workspaceTitle: who.workspaceTitle }).then((res) => {
                if (res && res.ok) { refreshPanel(); return; }
                alert('移除失败：' + ((res && res.reason) || '未知错误'));
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
              if (!who) { alert('无法确定是哪个工作区：请重新点开该工作区行的 ⋯ 菜单。'); return; }
              closeMenus();
              confirmBox(
                '删除工作区「' + who.title + '」',
                '将把整个项目文件夹（含里面所有文件，原样不改）连同它的会话记录一起移入：\n' +
                (cachedBin || 'C:\\Users\\<你>\\Documents\\DSH Recycle Bin') + '\n\n' +
                '回收条目里会写好「恢复说明.md」与「恢复.ps1」，随时可以还原。',
                '移入回收站',
                () => {
                  rpc('delete-workspace-by-title', { title: who.title }).then((res) => {
                    if (res && res.ok) { refreshPanel(); return; }
                    alert('删除失败：' + ((res && res.reason) || '未知错误'));
                  });
                },
              );
            }, true);
          }
          if (!labels.includes('清理与回收站…')) {
            const template = items[items.length - 1];
            const wrap = makeItem(template, '清理与回收站…', {
              onClick: (ev) => {
                ev.preventDefault(); ev.stopPropagation();
                closeMenus();
                togglePanel();
              },
            });
            const btn = wrap.querySelector('button[role="menuitem"]') || wrap;
            btn.style.color = 'inherit';
            const iconEl = btn.querySelector('span[class*="itemIcon"]');
            if (iconEl) iconEl.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">' +
              '<path d="M3 6h10v6.2c0 .7-.6 1.3-1.3 1.3H4.3c-.7 0-1.3-.6-1.3-1.3V6Z" stroke="currentColor" stroke-width="1.3"/>' +
              '<path d="M2.2 3.6h11.6M6.2 3.6V2.8c0-.4.3-.8.8-.8h2c.4 0 .8.3.8.8v.8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>';
            template.parentElement.parentElement.appendChild(wrap);
          }
        }
      }
    }

    let menuObserver = null;
    function installMenuDecorator(ctx) {
      document.addEventListener('pointerdown', rememberTrigger, true);
      document.addEventListener('click', rememberTrigger, true);
      menuObserver = new MutationObserver(() => decorateMenus());
      menuObserver.observe(document.body, { childList: true, subtree: true });
      const timer = setInterval(decorateMenus, 800);
      ctx.effect(() => () => {
        document.removeEventListener('pointerdown', rememberTrigger, true);
        document.removeEventListener('click', rememberTrigger, true);
        if (menuObserver) menuObserver.disconnect();
        clearInterval(timer);
      });
    }

    // ── plugin body ──
    // 不再往会话头部加「清理」芯片：删除会话在工作区/会话行的 ⋯ 菜单里，
    // 面板（工作区删除结果、已移除记录、回收站）从工作区菜单的「清理与回收站…」打开。
    function apply(ctx) {
      installMenuDecorator(ctx);
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  }
});
