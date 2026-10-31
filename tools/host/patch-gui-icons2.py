"""Patch 7: 把图标接到具体位置（快捷功能区、侧栏链接、日志标题、顶栏箭头）。

设计稿对应：.quick-icon svg 17、.side-link svg 17、.log-title>svg 15、.theme-trigger svg 14、
.text-btn svg 12。颜色：快捷图标 accent、侧栏未选中 muted / 选中 accent、
日志图标 accent、箭头 muted。
"""
import io

P = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    # 1) 快捷功能区：直接用图标名
    ("        for idx, (key, title, sub, glyph) in enumerate((\n"
     "                ('token', '查看 Token', '访问凭证与连接信息', '⚿'),\n"
     "                ('plugins', '管理插件', '安装、启用与配置扩展', '⊞'),\n"
     "                ('update', '检查更新', '获取最新的 dsh 与 Node', '↓'),\n"
     "                ('folder', '数据目录', '浏览配置与本地数据', '▤'))):\n"
     "            quick.attach(self._quick_action(key, title, sub, glyph), idx, 0, 1, 1)",
     "        for idx, (key, title, sub, icon) in enumerate((\n"
     "                ('token', '查看 Token', '访问凭证与连接信息', 'key'),\n"
     "                ('plugins', '管理插件', '安装、启用与配置扩展', 'puzzle'),\n"
     "                ('update', '检查更新', '获取最新的 dsh 与 Node', 'update'),\n"
     "                ('folder', '数据目录', '浏览配置与本地数据', 'folder'))):\n"
     "            quick.attach(self._quick_action(key, title, sub, icon), idx, 0, 1, 1)"),
    # 2) _quick_action 支持图标名（也兼容旧的字形）
    ("    def _quick_action(self, key, title, sub, glyph):",
     "    def _quick_action(self, key, title, sub, glyph):\n"
     "        icon_name = glyph if glyph in _ICON_NAMES else GLYPH_ICON.get(glyph)"),
    ("        box.pack_start(self._chip(glyph, 'quick-icon', width=34, height=34,\n"
     "                                  valign=Gtk.Align.CENTER), False, False, 0)",
     "        box.pack_start(self._chip('', 'quick-icon', width=34, height=34,\n"
     "                                  valign=Gtk.Align.CENTER, icon=icon_name,\n"
     "                                  role='accent', icon_size=17), False, False, 0)"),
    # 3) 侧栏链接：图标 + 文字
    ("        self.btn_overview = self._button('', '▦   实例概览', 'side-link', 'selected',\n"
     "                                         handler=lambda *a: self._show_page('dashboard'))",
     "        self.btn_overview = self._button('', '实例概览', 'side-link', 'selected',\n"
     "                                         handler=lambda *a: self._show_page('dashboard'),\n"
     "                                         icon='grid', icon_role='accent', icon_size=17)"),
    ("        self.btn_settings = self._button('settings', '⚙   管理器设置', 'side-link')",
     "        self.btn_settings = self._button('settings', '管理器设置', 'side-link',\n"
     "                                         icon='settings', icon_role='muted', icon_size=17)"),
    ("        self.btn_help = self._button('', '？   使用帮助', 'side-link', handler=self.on_help)",
     "        self.btn_help = self._button('', '使用帮助', 'side-link', handler=self.on_help,\n"
     "                                    icon='help', icon_role='muted', icon_size=17)"),
    # 4) 日志标题图标
    ("        lhead.pack_start(self._label('▶', 'log-icon'), False, False, 0)",
     "        lhead.pack_start(self._icon('terminal', 'accent', 15), False, False, 0)"),
    # 5) 顶栏主题触发器的箭头
    ("        inner.pack_start(self._label('⌄', 'glyph'), False, False, 0)",
     "        inner.pack_start(self._icon('chevron', 'muted', 14), False, False, 0)"),
    # 6) 「查看完整日志 →」
    ("        view_btn = self._button('', '查看完整日志  →', 'text-btn', handler=self.on_view_log)",
     "        view_btn = self._button('', '查看完整日志', 'text-btn', handler=self.on_view_log,\n"
     "                                icon='arrow', icon_role='accent', icon_size=12)"),
]


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:70])
            continue
        s = s.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched %d/%d; missing: %s' % (len(SUBS) - len(missing), len(SUBS),
                                         missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
