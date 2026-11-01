"""插件对话框：显示"从 GitHub 发现"的来源与刷新按钮。

- 打开时先用缓存（避免闪空），并在后台拉一次 GitHub；
- 加一个「刷新 GitHub 列表」按钮，手动重拉；
- 顶部一行小字显示来源：GitHub · cuteG41cute（topic: dsh-plugin）+ 抓取时间。
"""
import io

P = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    # 1) 来源行 + 缓存引导
    ("        intro.get_style_context().add_class('dialog-sub')\n"
     "        area.pack_start(intro, False, False, 0)",
     "        intro.get_style_context().add_class('dialog-sub')\n"
     "        area.pack_start(intro, False, False, 0)\n"
     "\n"
     "        src_lbl = Gtk.Label(xalign=0)\n"
     "        src_lbl.get_style_context().add_class('dim-label')\n"
     "        area.pack_start(src_lbl, False, False, 0)\n"
     "\n"
     "        def refresh_source_label():\n"
     "            where, when = plug.source_info()\n"
     "            src_lbl.set_text('来源：%s%s' % (where, ('　抓取于 %s' % when) if when else ''))\n"
     "        plug.bootstrap_cache()\n"
     "        refresh_source_label()"),
    # 2) 多一个按钮
    ("        btn_import = Gtk.Button(label='导入本地包…')\n"
     "        for btn in (btn_install, btn_uninstall, btn_import, btn_refresh, btn_repo):",
     "        btn_import = Gtk.Button(label='导入本地包…')\n"
     "        btn_gh = Gtk.Button(label='刷新 GitHub 列表')\n"
     "        for btn in (btn_install, btn_uninstall, btn_import, btn_refresh, btn_repo, btn_gh):"),
    # 3) 接上刷新逻辑
    ("        btn_refresh.connect('clicked', lambda *a: fill(select=current()))\n"
     "        btn_repo.connect('clicked', open_repo)",
     "        btn_refresh.connect('clicked', lambda *a: fill(select=current()))\n"
     "        btn_repo.connect('clicked', open_repo)\n"
     "\n"
     "        def refresh_github(*_):\n"
     "            state['busy'] = True\n"
     "            btn_gh.set_sensitive(False)\n"
     "            note.set_text('正在从 GitHub 拉取带 dsh-plugin 标签的仓库…')\n"
     "\n"
     "            def work():\n"
     "                try:\n"
     "                    items, fetched = plug.refresh_github()\n"
     "                    err = ''\n"
     "                except Exception as exc:\n"
     "                    items, fetched, err = [], '', str(exc)\n"
     "\n"
     "                def done():\n"
     "                    state['busy'] = False\n"
     "                    btn_gh.set_sensitive(True)\n"
     "                    refresh_source_label()\n"
     "                    fill(select=current())\n"
     "                    if err:\n"
     "                        note.set_text('拉取失败：%s（列表沿用上次结果）' % err)\n"
     "                    else:\n"
     "                        note.set_text('已刷新：GitHub 上 %d 个带 dsh-plugin 标签的仓库' % len(items))\n"
     "                    return False\n"
     "                GLib.idle_add(done)\n"
     "\n"
     "            threading.Thread(target=work, daemon=True).start()\n"
     "\n"
     "        btn_gh.connect('clicked', refresh_github)"),
    # 4) 说明列补上更新时间/星标，一眼看出新旧
    ("                it = store.append([item['id'], '%s · %s' % (src, item['desc']),\n"
     "                                   label, st.get('version') or '-'])",
     "                extra = ''\n"
     "                if item.get('updated'):\n"
     "                    extra = '　★%s · 更新 %s' % (item.get('stars', 0), item['updated'])\n"
     "                it = store.append([item['id'], '%s · %s%s' % (src, item['desc'], extra),\n"
     "                                   label, st.get('version') or '-'])"),
]

MARK = "btn_gh = Gtk.Button(label='刷新 GitHub 列表')"


def main():
    s = io.open(P, encoding='utf-8').read()
    if MARK in s:
        print('already patched')
        return 0
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('gui patched, missing: %s' % (missing if missing else 'none'))
    return 0 if not missing else 1


if __name__ == '__main__':
    raise SystemExit(main())
