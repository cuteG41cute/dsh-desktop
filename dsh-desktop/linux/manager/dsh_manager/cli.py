# -*- coding: utf-8 -*-
"""dsh-manager 命令行入口（--headless）与 GUI 启动。

用法：
  dsh-manager                                 打开图形界面
  dsh-manager --headless list [--json]
  dsh-manager --headless install --prefix P [--dsh V] [--node V] [--port N] [--label L]
  dsh-manager --headless update  --prefix P [--dsh V] [--node V]
  dsh-manager --headless repair  --prefix P
  dsh-manager --headless uninstall --prefix P [--yes]
  dsh-manager --headless start|stop|open|status --prefix P [--json]
  dsh-manager --headless versions [--kind dsh|node] [--json]
  dsh-manager --version
"""
import argparse
import json
import sys

from .core import DEFAULT_DSH, DEFAULT_NODE, MANAGER_VERSION, Manager


def _print_instances(mgr, as_json):
    items = [i.to_dict() for i in mgr.list_instances()]
    if as_json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0
    if not items:
        print('（还没有实例）用 `dsh-manager --headless install --prefix <目录>` 建一个')
        return 0
    print('%-22s %-28s %-10s %-12s %-7s %s' % ('名称', '安装位置', 'dsh', 'node', '端口', '状态'))
    for it in items:
        print('%-22s %-28s %-10s %-12s %-7s %s' % (
            it['label'], it['prefix'], it['dsh'] or '-', it['node'] or '-', it['port'], it['status']))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if '--version' in argv:
        print('dsh-manager %s' % MANAGER_VERSION)
        return 0

    if '--gui-check' in argv:
        # 只构造窗口，不进入主循环：把启动期的异常原样打出来（排障用）
        try:
            from .gui import ManagerWindow
            win = ManagerWindow()
            win.destroy()
        except Exception:
            import traceback
            traceback.print_exc()
            return 1
        print('OK: 图形界面能构造出来（v%s）' % MANAGER_VERSION)
        return 0

    if '--headless' not in argv:
        # 图形界面
        try:
            from .gui import run_gui
        except ImportError as exc:
            print('缺少图形界面依赖（%s）。\n'
                  '请安装：sudo apt install -y python3-gi gir1.2-gtk-3.0\n'
                  '或者用命令行：dsh-manager --headless list' % exc, file=sys.stderr)
            return 1
        try:
            return run_gui()
        except Exception:
            # 绝不再“闪一下就没了”：堆栈落盘 + 打到终端，然后用纯 GTK 弹一个错误窗
            import traceback
            tb = traceback.format_exc()
            try:
                from .core import config_dir, manager_log_path
                import os
                os.makedirs(config_dir(), exist_ok=True)
                with open(os.path.join(config_dir(), 'crash.log'), 'a', encoding='utf-8') as fh:
                    fh.write('\n===== %s (%s) =====\n' % (MANAGER_VERSION, 'gui'))
                    fh.write(tb)
                traceback.print_exc()
                sys.stderr.write('（完整堆栈也写进了 %s）\n' % os.path.join(config_dir(), 'crash.log'))
            except Exception:
                traceback.print_exc()
            try:
                from .gui import show_crash_dialog
                show_crash_dialog(tb)
            except Exception:
                pass
            return 1

    rest = argv[argv.index('--headless') + 1:]
    if not rest:
        print(__doc__)
        return 2
    cmd, rest = rest[0], rest[1:]

    ap = argparse.ArgumentParser(prog='dsh-manager --headless ' + cmd, add_help=True)
    ap.add_argument('--prefix')
    ap.add_argument('--dsh', default=None)
    ap.add_argument('--node', default=None)
    ap.add_argument('--port', type=int, default=None)
    ap.add_argument('--label', default=None)
    ap.add_argument('--root', default=None)
    ap.add_argument('--kind', default='dsh')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--yes', action='store_true')
    ap.add_argument('--rebuild', action='store_true',
                    help='open：即使已有窗口也先杀掉重开（画面坏掉时用）')
    ap.add_argument('--id', default=None)
    ap.add_argument('--tarball', default=None)
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args(rest)

    mgr = Manager(root=args.root)
    if args.verbose:
        import os
        os.environ['DSH_MANAGER_VERBOSE'] = '1'

    if cmd == 'list':
        return _print_instances(mgr, args.json)

    if cmd == 'versions':
        if args.kind == 'node':
            vers = mgr.available_node_versions()
        else:
            vers = mgr.available_dsh_versions()
        print(json.dumps(vers, ensure_ascii=False) if args.json else '\n'.join(vers))
        return 0

    if not args.prefix and cmd not in ('list', 'versions'):
        print('需要 --prefix <安装目录>', file=sys.stderr)
        return 2

    if cmd == 'install':
        ok, msg, inst = mgr.install(args.prefix, args.dsh or DEFAULT_DSH,
                                    args.node or DEFAULT_NODE, args.port, args.label)
        print(('✔ ' if ok else '✘ ') + msg)
        return 0 if ok else 1

    if cmd == 'update':
        ok, msg, inst = mgr.update(args.prefix, args.dsh, args.node)
        print(('✔ ' if ok else '✘ ') + msg)
        return 0 if ok else 1

    if cmd == 'repair':
        ok, msg, inst = mgr.repair(args.prefix)
        print(('✔ ' if ok else '✘ ') + msg)
        return 0 if ok else 1

    if cmd == 'uninstall':
        if not args.yes:
            print('（--yes 才真的删）将删除：%s' % args.prefix)
            return 2
        ok, msg = mgr.uninstall(args.prefix)
        print(('✔ ' if ok else '✘ ') + msg)
        return 0 if ok else 1

    # ---- 插件管理（第一阶段：从我们自己的 GitHub 仓库装/卸）----
    if cmd in ('plugins', 'install-plugin', 'uninstall-plugin'):
        from . import plugins as plug
        if cmd == 'plugins' or args.json and not args.id:
            status = plug.installed(mgr.instance_at(args.prefix))
            items = []
            for item in plug.all_entries(mgr.instance_at(args.prefix)):
                st = status.get(item['id'], {})
                items.append({
                    'id': item['id'], 'name': item['name'], 'repo': item['repo'],
                    'desc': item['desc'], 'installed': st.get('installed', False),
                    'registered': st.get('registered', False),
                    'version': st.get('version', ''),
                })
            if args.json:
                print(json.dumps(items, ensure_ascii=False, indent=2))
            else:
                print('%-18s %-14s %-8s %-10s %s'
                      % ('id', '名称', '状态', '版本', '仓库'))
                for it in items:
                    print('%-18s %-14s %-8s %-10s %s'
                          % (it['id'], it['name'],
                             '已安装' if it['installed'] else '未安装',
                             it['version'] or '-', it['repo']))
            return 0

        inst = mgr.instance_at(args.prefix)
        entry = plug.entry_for(inst, args.id)
        # 卸载：即使目录里没有这个 id（例如本地导入的包），也按 id 直接卸
        if not entry and not (cmd == 'uninstall-plugin' and args.id):
            print('目录里没有这个插件：%s（可用：%s）'
                  % (args.id, ', '.join(i['id'] for i in plug.all_entries(inst))), file=sys.stderr)
            return 2
        log = lambda line: print('  ' + str(line), flush=True)
        if cmd == 'install-plugin' and args.tarball:
            ok, msg = plug.install_from_tarball(inst, args.tarball, log=log)
        elif cmd == 'install-plugin':
            ok, msg = plug.install(inst, entry, log=log)
        else:
            ok, msg = plug.uninstall(inst, entry=entry, pid=args.id, log=log)
        print(('✔ ' if ok else '✘ ') + msg)
        return 0 if ok else 1
    if cmd in ('start', 'stop', 'open', 'rebuild', 'reload', 'repaint', 'status'):
        inst = mgr.instance_at(args.prefix)
        if cmd == 'start':
            ok, msg = inst.start()
        elif cmd == 'stop':
            ok, msg = inst.stop()
        elif cmd == 'open':
            ok, msg = inst.open_window(rebuild=getattr(args, 'rebuild', False))
        elif cmd == 'rebuild':
            ok, msg = inst.open_window(rebuild=True)
        elif cmd == 'reload':
            ok, msg = inst.reload_page(), '已让窗口重新加载页面'
            if not ok:
                msg = '窗口没响应 reload（旧版窗口？）'
        elif cmd == 'repaint':
            ok, msg = inst.repaint_window(), '已请求整窗重绘'
            if not ok:
                msg = '窗口没响应 repaint（旧版窗口？）'
        else:
            ok, msg = True, json.dumps(inst.to_dict(), ensure_ascii=False)
        print(('✔ ' if ok else '✘ ') + msg)
        return 0 if ok else 1

    print('不认识的命令：%s' % cmd, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
