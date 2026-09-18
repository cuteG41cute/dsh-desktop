// dsh-file-history — Client half (static / composition plugin)
//
// Browser bundle consumed by the client module loader (window.__ModuleLoader__).
// 与宿主通过插件自己的 JSON API（POST /dsh-file-history/api）通信：
// 右上角「备份」状态芯片 + 悬停面板（实时流水、代数/占用统计、总开关）。
// 观测口径与 monitor.ps1 一致：status.json 的 at/snapshots/lastError + manifest.jsonl 的最近条目。

window.__ModuleLoader__.load({
  id: 'dsh-file-history',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' })
    const react = require('react')

    const API = '/dsh-file-history/api'

    function rpc(method, args) {
      return fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ method: method, args: args || {} }),
      })
        .then((response) => response.json())
        .catch((error) => ({ ok: false, reason: String((error && error.message) || error) }))
    }

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
    }

    const panelStyle = {
      position: 'absolute',
      top: 'calc(100% + 6px)',
      right: 0,
      width: 380,
      maxHeight: 460,
      overflowY: 'auto',
      zIndex: 400,
      background: 'var(--dsw-alias-bg-base, #fff)',
      border: '1px solid var(--dsw-alias-divider, rgba(128,128,128,0.35))',
      borderRadius: 10,
      boxShadow: '0 8px 28px rgba(0,0,0,0.18)',
      padding: 12,
      fontSize: 12,
      lineHeight: '18px',
      color: 'var(--dsw-alias-label-primary, #222)',
      textAlign: 'left',
      cursor: 'default',
    }

    const labelStyle = { color: 'var(--dsw-alias-label-caption, #9a9a9a)' }
    const valueStyle = { color: 'var(--dsw-alias-label-primary, #222)' }
    const rowStyle = { display: 'flex', gap: 8, alignItems: 'baseline', marginBottom: 4 }

    function row(label, value, mono) {
      return react.createElement('div', { key: 'r-' + label, style: rowStyle }, [
        react.createElement('span', { key: 'l', style: { ...labelStyle, flex: '0 0 84px' } }, label),
        react.createElement('span', {
          key: 'v',
          style: { ...valueStyle, flex: '1 1 auto', wordBreak: 'break-all', fontFamily: mono ? 'ui-monospace, Consolas, monospace' : 'inherit' },
          title: typeof value === 'string' ? value : undefined,
        }, value),
      ])
    }

    function formatSize(bytes) {
      const n = Number(bytes) || 0
      if (n < 1024) return n + ' B'
      if (n < 1048576) return (n / 1024).toFixed(1) + ' KB'
      return (n / 1048576).toFixed(2) + ' MB'
    }

    function ageText(ms) {
      if (!ms || ms <= 0) return '(无)'
      const seconds = Math.round(ms / 1000)
      if (seconds < 60) return seconds + ' 秒前'
      const minutes = Math.round(seconds / 60)
      if (minutes < 60) return minutes + ' 分钟前'
      const hours = Math.round(minutes / 60)
      if (hours < 48) return hours + ' 小时前'
      return Math.round(hours / 24) + ' 天前'
    }

    function kindColor(kind) {
      if (kind === 'restore') return 'var(--dsw-static-deepseek-500, #4d6bfe)'
      if (kind === 'revert_turn') return '#a855f7'
      if (kind === 'snapshot') return '#16a34a'
      return 'var(--dsw-alias-label-caption, #9a9a9a)'
    }

    function apply(ctx) {
      const slots = ctx.get('slots')
      if (slots === undefined) return

      // ── 右上角状态芯片 + 面板 ──────────────────────────────────────────
      slots.inject('conversation.session.header.utilities', () => slots.register(
        { name: 'conversation.session.header.utilities', id: 'file-history-status', order: 30 },
        (props) => {
          const sessionId = props && props.sessionId ? props.sessionId : undefined
          const [state, setState] = react.useState(null)
          const [error, setError] = react.useState(null)
          const [open, setOpen] = react.useState(false)
          const [now, setNow] = react.useState(Date.now())
          const wrapRef = react.useRef(null)

          const pull = () => {
            rpc('state', { sessionId: sessionId }).then((result) => {
              if (result && result.ok === true) {
                setState(result)
                setError(null)
              } else {
                setState(result || null)
                setError((result && result.reason) || '状态读取失败')
              }
            })
          }

          // 面板打开时高频刷新（肉眼可见的实时流水），关闭时低频刷新维持灯色。
          react.useEffect(() => {
            let alive = true
            const tick = () => {
              if (!alive) return
              setNow(Date.now())
              pull()
            }
            tick()
            const interval = setInterval(tick, open ? 2000 : 30000)
            return () => { alive = false; clearInterval(interval) }
          }, [sessionId, open])

          // 点击组件与面板之外关闭。
          react.useEffect(() => {
            if (!open) return undefined
            const onDown = (event) => {
              const wrap = wrapRef.current
              if (wrap && !wrap.contains(event.target)) setOpen(false)
            }
            const onKey = (event) => { if (event.key === 'Escape') setOpen(false) }
            document.addEventListener('mousedown', onDown)
            document.addEventListener('keydown', onKey)
            return () => {
              document.removeEventListener('mousedown', onDown)
              document.removeEventListener('keydown', onKey)
            }
          }, [open])

          const healthy = state && state.ok === true && !error
          const primaryError = error || (state && state.status && state.status.lastError ? String(state.status.lastError.reason || '备份失败') : null)
          const ageMs = state && state.refreshedAt ? now - state.refreshedAt : null
          const dotColor = primaryError
            ? 'var(--dsw-alias-state-error-primary, #d92d20)'
            : !healthy
              ? 'var(--dsw-alias-label-caption, #9a9a9a)'
              : (state && state.status && state.status.atMs && now - state.status.atMs < 120000)
                ? '#16a34a'
                : 'var(--dsw-static-deepseek-500, #4d6bfe)'
          const projectSettings = (state && state.settings) || {}
          const enabled = projectSettings.enabled !== false
          const scope = projectSettings.scope === 'project' ? 'project' : 'inherit'
          // 芯片上的数字＝**当前占用**（现存备份文件总字节，会随清理降下来），不是历史累计次数；
          // 次数仍在面板里（「备份次数」一行）。
          const stat = (state && state.stat) || { count: 0, bytes: 0 }
          const chipText = primaryError
            ? '备份异常'
            : (enabled ? '备份 ' + formatSize(stat.bytes) : '备份 关')
          const title = primaryError
            ? '改前自动备份：' + primaryError + '（点击查看）'
            : '改前自动备份（本项目：' + (enabled ? '开启' : '关闭') + (scope === 'project' ? '，项目单独设置' : '，继承全局默认') + '）'
              + '；当前占用 ' + formatSize(stat.bytes) + ' / ' + stat.count + ' 份'
              + '，累计备份 ' + ((state && state.status && state.status.snapshots) || 0) + ' 次'
              + '。（点击查看实时状态与项目级开关）'

          // 开关是项目级的：scope=project 只改当前项目；scope=global 改全局默认。
          const setEnabled = (wanted, targetScope) => {
            rpc('set-enabled', { sessionId: sessionId, enabled: wanted, scope: targetScope || 'project' }).then((result) => {
              if (result && result.ok === true) pull()
              else setError((result && result.reason) || '写入失败')
            })
          }
          const resetProject = () => {
            rpc('reset-project', { sessionId: sessionId }).then((result) => {
              if (result && result.ok === true) pull()
              else setError((result && result.reason) || '写入失败')
            })
          }

          const pieces = []
          pieces.push(react.createElement('button', {
            key: 'chip',
            onClick: () => setOpen(!open),
            title: title,
            style: chipStyle,
          }, [
            react.createElement('span', { key: 'd', style: { width: 8, height: 8, borderRadius: '50%', display: 'inline-block', flex: 'none', background: dotColor } }),
            react.createElement('span', { key: 't' }, chipText),
          ]))

          if (open) {
            const body = []
            if (!healthy) {
              body.push(react.createElement('div', { key: 'offline', style: { color: 'var(--dsw-alias-state-error-primary, #d92d20)', marginBottom: 8 } },
                '读不到备份状态：' + (primaryError || '插件可能未加载')))
              body.push(react.createElement('div', { key: 'hint', style: { ...labelStyle, marginBottom: 8 } },
                '确认 <项目>/.dsh-backup 是否存在；若不存在，重启 dsh 服务后再看。'))
            } else {
              const status = state.status || {}
              const stat = state.stat || {}
              body.push(react.createElement('div', { key: 'head', style: { fontWeight: 600, marginBottom: 8 } },
                '改前自动备份 · ' + (state.projectName || state.projectDir || '')))
              body.push(row('状态', primaryError ? '异常' : (enabled ? '运行中' : '已关闭')))
              body.push(row('开关范围', scope === 'project' ? '仅本项目（项目级单独设置）' : '跟随全局默认（' + (projectSettings.globalEnabled === false ? '全局关' : '全局开') + '）'))
              body.push(row('最后活动', (status.at || '(无)') + '（' + ageText(now - (status.atMs || 0)) + '）'))
              body.push(row('备份次数', String(status.snapshots || 0)))
              body.push(row('保留代数', '每个源文件最近 ' + (status.retainedPerFile || state.settings.maxGenerations || 5) + ' 代'))
              body.push(row('当前占用', stat.count + ' 份 · ' + formatSize(stat.bytes)))
              if (status.lastBackup) body.push(row('最近备份', String(status.lastBackup.at || '') + '  ' + String(status.lastBackup.path || ''), true))
              if (status.lastRestore) body.push(row('最近还原', String(status.lastRestore.at || '') + '  ' + String(status.lastRestore.path || ''), true))
              if (status.lastError) body.push(react.createElement('div', { key: 'err', style: { color: 'var(--dsw-alias-state-error-primary, #d92d20)', marginTop: 6 } },
                '最近错误：' + String(status.lastError.reason || '') + '（该次写入已被拦下）'))
              body.push(react.createElement('div', { key: 'dir', style: { ...labelStyle, marginTop: 6, wordBreak: 'break-all' } }, status.backupDir || ''))

              // ── 项目级开关 ──
              body.push(react.createElement('div', { key: 'sw-title', style: { ...labelStyle, marginTop: 8, marginBottom: 4 } },
                '本项目开关（只影响 ' + (state.projectName || '当前项目') + '）'))
              body.push(react.createElement('div', { key: 'sw-row', style: { display: 'flex', gap: 6, flexWrap: 'wrap' } }, [
                react.createElement('button', {
                  key: 'proj',
                  onClick: () => setEnabled(!enabled, 'project'),
                  style: { ...chipStyle, cursor: 'pointer' },
                }, enabled ? '关闭本项目备份' : '开启本项目备份'),
                scope === 'project'
                  ? react.createElement('button', {
                    key: 'reset',
                    onClick: resetProject,
                    title: '删除本项目的单独设置，改为跟随全局默认',
                    style: { ...chipStyle, cursor: 'pointer' },
                  }, '改为跟随全局默认')
                  : null,
              ].filter(Boolean)))
              body.push(react.createElement('div', { key: 'sw-global', style: { display: 'flex', gap: 6, alignItems: 'center', marginTop: 6, flexWrap: 'wrap' } }, [
                react.createElement('span', { key: 'l', style: labelStyle }, '全局默认：' + (projectSettings.globalEnabled === false ? '关' : '开')),
                react.createElement('button', {
                  key: 'gflip',
                  onClick: () => setEnabled(projectSettings.globalEnabled === false, 'global'),
                  title: '只影响没有单独设置过的项目',
                  style: { ...chipStyle, cursor: 'pointer' },
                }, '改为「全局' + (projectSettings.globalEnabled === false ? '开' : '关') + '」'),
              ]))
            }

            // 实时流水（最近 12 条），每条一行：时间 · 动作 · 文件名
            const events = (state && Array.isArray(state.events) ? state.events : []).slice(0, 12)
            body.push(react.createElement('div', { key: 'sep', style: { borderTop: '1px solid var(--dsw-alias-divider, rgba(128,128,128,0.25))', margin: '10px 0 6px' } }))
            body.push(react.createElement('div', { key: 'rt', style: { ...labelStyle, marginBottom: 4 } },
              events.length ? '实时流水（每 2 秒刷新）' : '还没有备份记录：覆盖一个已存在的文件后会出现'))
            for (let index = 0; index < events.length; index += 1) {
              const event = events[index]
              body.push(react.createElement('div', {
                key: 'ev-' + index,
                style: { display: 'flex', gap: 6, alignItems: 'baseline', padding: '1px 0' },
                title: event.backup || '',
              }, [
                react.createElement('span', { key: 't', style: { ...labelStyle, flex: '0 0 108px', fontFamily: 'ui-monospace, Consolas, monospace', fontSize: 11 } }, String(event.at || '').slice(5)),
                react.createElement('span', { key: 'k', style: { color: kindColor(event.kind), flex: '0 0 72px', fontSize: 11 } }, String(event.kind || '')),
                react.createElement('span', { key: 'f', style: { flex: '1 1 auto', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, String(event.file || '')),
              ]))
            }
            if (state && state.manifestPath) {
              body.push(react.createElement('div', { key: 'mp', style: { ...labelStyle, marginTop: 8, wordBreak: 'break-all' } }, '流水文件：' + state.manifestPath))
            }
            body.push(react.createElement('div', { key: 'fresh', style: { ...labelStyle, marginTop: 4 } },
              '本次读取于 ' + ageText(ageMs) + ' · 状态文件 ' + String(state.statusPath || '')))

            pieces.push(react.createElement('div', {
              key: 'panel',
              style: panelStyle,
              onClick: (event) => event.stopPropagation(),
            }, body))
          }

          return react.createElement('div', {
            key: 'wrap',
            ref: wrapRef,
            style: { position: 'relative', display: 'inline-flex', alignItems: 'center' },
          }, pieces)
        },
      ))

      // ── 设置里的同一开关（与记忆库一致的入口） ─────────────────────────
      slots.inject('settings.general.item', () => slots.register(
        { name: 'settings.general.item', id: 'file-history-settings', order: 40 },
        () => {
          const [state, setState] = react.useState(null)
          const pull = () => {
            rpc('state', {}).then((result) => { if (result) setState(result) })
          }
          react.useEffect(() => { pull() }, [])
          const settings = (state && state.settings) || null
          const enabled = settings ? settings.enabled !== false : null
          const scope = settings && settings.scope === 'project' ? 'project' : 'inherit'
          const text = enabled === null
            ? '改前自动备份：读取中…'
            : ('改前自动备份（本项目）：' + (enabled ? '已开启' : '已关闭') + (scope === 'project' ? ' · 项目单独设置' : ' · 跟随全局默认'))
          const write = (method, payload) => {
            rpc(method, payload).then((result) => {
              if (result && result.ok === true) pull()
            })
          }
          return react.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } }, [
            react.createElement('div', { key: 'title', style: { fontWeight: 600 } }, text),
            react.createElement('div', { key: 'desc', style: { ...labelStyle, fontSize: 12 } },
              '开关按项目独立控制：这里切的是「当前项目」，其它项目互不影响。任何 write/edit 覆盖已存在文件之前，自动把原文备份进该项目 .dsh-backup/（源文件名+时间戳，每个文件只保留最近若干代）。'),
            react.createElement('div', { key: 'row', style: { display: 'flex', gap: 6, flexWrap: 'wrap' } }, [
              react.createElement('button', {
                key: 'flip',
                style: { ...chipStyle, cursor: 'pointer' },
                disabled: enabled === null,
                onClick: () => { if (enabled !== null) write('set-enabled', { enabled: !enabled, scope: 'project' }) },
              }, enabled === null ? '…' : (enabled ? '关闭本项目备份' : '开启本项目备份')),
              scope === 'project'
                ? react.createElement('button', {
                  key: 'reset',
                  style: { ...chipStyle, cursor: 'pointer' },
                  onClick: () => write('reset-project', {}),
                }, '改为跟随全局默认')
                : null,
              settings
                ? react.createElement('button', {
                  key: 'global',
                  style: { ...chipStyle, cursor: 'pointer' },
                  title: '只影响没有单独设置过的项目',
                  onClick: () => write('set-enabled', { enabled: settings.globalEnabled === false, scope: 'global' }),
                }, '全局默认：' + (settings.globalEnabled === false ? '关' : '开') + ' → 切换')
                : null,
            ].filter(Boolean)),
          ])
        },
      ))
    }

    exports.apply = apply
    exports.inject = ['slots']
    return module.exports
  },
})
