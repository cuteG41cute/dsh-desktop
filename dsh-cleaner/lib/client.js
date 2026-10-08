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

    const inject = ['slots'];

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

    /** 两步确认按钮：第一下变「确认删除？」，3 秒内再点才执行。 */
    function dangerButton(label, onConfirm) {
      const btn = document.createElement('button');
      btn.textContent = label;
      btn.style.cssText = 'padding:2px 8px;border-radius:6px;border:1px solid var(--dsw-alias-divider,rgba(128,128,128,0.35));' +
        'background:transparent;color:inherit;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap;';
      let armed = false;
      let timer = 0;
      btn.addEventListener('click', () => {
        if (!armed) {
          armed = true;
          btn.textContent = '确认删除？';
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
        btn.textContent = '删除中…';
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
      overlay.append(panelNote('删除 = 移入 ~/.dsh/trash/session-cleaner（可恢复）。正在打开的会话会被拒绝。', null));

      const busy = document.createElement('div');
      busy.textContent = '读取中…';
      busy.style.cssText = 'font-size:12px;opacity:0.7;';
      overlay.append(busy);

      let trashEntries = [];
      rpc('trash-list', {}).then((r) => { if (r && r.ok) trashEntries = r.entries || []; });

      rpc('list', {}).then((r) => {
        if (!overlay.isConnected) return;
        busy.remove();
        if (!r || r.ok !== true) {
          overlay.append(panelNote('读取失败：' + ((r && r.reason) || '未知错误'), 'error'));
          return;
        }
        const workspaces = r.workspaces || [];
        const orphans = r.orphans || [];
        const totalBytes = workspaces.reduce((s, w) => s + (w.bytes || 0), 0);
        const totalSessions = workspaces.reduce((s, w) => s + w.sessions.length, 0);
        overlay.append(panelNote(`${workspaces.length} 个工作区 · ${totalSessions} 个会话 · 共 ${fmtBytes(totalBytes)}` +
          (orphans.length ? ` · 孤儿 ${orphans.length} 个` : ''), null));

        for (const ws of workspaces) {
          const group = document.createElement('div');
          group.style.cssText = 'border-top:1px solid var(--dsw-alias-divider,rgba(128,128,128,0.25));padding:6px 0 2px;';
          const head = document.createElement('div');
          head.style.cssText = 'display:flex;align-items:center;gap:8px;';
          head.append(rowLabel(
            ws.title || '(未命名工作区)',
            `${ws.sessions.length} 个会话 · ${fmtBytes(ws.bytes)} · ${ws.path || ''}`,
          ));
          if (ws.sessions.length > 0 || true) {
            head.append(dangerButton('删除工作区', () => {
              return rpc('delete-workspace', { workspaceId: ws.id }).then((res) => {
                if (res && res.ok) { refreshPanel(); return; }
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
            if (!s.open) {
              row.append(dangerButton('删除', () => {
                return rpc('delete-session', { sessionId: s.id }).then((res) => {
                  if (res && res.ok) { refreshPanel(); return; }
                  alert('删除失败：' + ((res && res.reason) || '未知错误'));
                  refreshPanel();
                });
              }));
            } else {
              const tag = document.createElement('span');
              tag.textContent = '使用中';
              tag.style.cssText = 'font-size:11px;opacity:0.6;white-space:nowrap;';
              row.append(tag);
            }
            group.append(row);
          }
          overlay.append(group);
        }

        if (orphans.length > 0) {
          overlay.append(sectionTitle('孤儿会话（不在任何工作区登记里，多为接口任务残留）'));
          for (const o of orphans) {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:3px 0;';
            row.append(rowLabel(o.id, [fmtBytes(o.bytes), o.mtime ? fmtWhen(o.mtime) : null].filter(Boolean).join(' · ')));
            if (!o.open) {
              row.append(dangerButton('删除', () => {
                return rpc('delete-orphan', { sessionId: o.id }).then((res) => {
                  if (res && res.ok) { refreshPanel(); return; }
                  alert('删除失败：' + ((res && res.reason) || '未知错误'));
                  refreshPanel();
                });
              }));
            }
            overlay.append(row);
          }
        }

        if (trashEntries.length > 0) {
          const details = document.createElement('details');
          details.style.cssText = 'margin-top:10px;';
          const summary = document.createElement('summary');
          summary.textContent = `回收目录（${trashEntries.length} 条，可恢复）`;
          summary.style.cssText = 'cursor:pointer;font-size:12px;opacity:0.8;';
          details.append(summary);
          for (const t of trashEntries) {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:3px 0;';
            row.append(rowLabel(t.sessionId, [fmtBytes(t.bytes), t.when ? t.when.slice(0, 19).replace('T', ' ') : null].filter(Boolean).join(' · ')));
            const btn = document.createElement('button');
            btn.textContent = '恢复';
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

    // ── header chip ──
    function CleanerChip() {
      return react.createElement('button', {
        onClick: togglePanel,
        title: '清理：删除会话与工作区（移入可恢复的回收目录）',
        style: chipStyle,
      }, [
        react.createElement('span', { key: 't' }, '清理'),
      ]);
    }

    // ── plugin body ──
    function apply(ctx) {
      const slots = ctx.get('slots');
      if (slots === undefined) return;
      slots.inject('conversation.session.header.utilities', () => slots.register(
        { name: 'conversation.session.header.utilities', id: 'dsh-cleaner-chip', order: 22 },
        (props) => CleanerChip(props),
      ));
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  }
});
