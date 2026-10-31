"""Patch 20: 按 DESIGN_SPEC.md §2.5 实现两档响应式断点。

设计稿里是 CSS 媒体查询：
  @media(max-width:1280px)  外边距 14 / 侧栏 220 / 内容与顶栏 padding 22 /
                            快捷功能两列 / 快捷卡高 70 / 概览卡 1.35:1 /
                            日志卡 margin 16 / 卡片 padding 16 / 隐藏控制卡副说明
  @media(max-height:850px)  内容 padding-top 18 / 标题区 margin 15 / 隐藏页面说明 /
                            卡 min-height 190 / 快捷区 16 / 日志卡 15 /
                            品牌下边距 18 / 侧栏底部 14 / 运行环境卡 10 / 隐藏页脚

GTK3 没有媒体查询，所以：窗口尺寸变化时给窗口加 `narrow` / `short` 类，
由主题 CSS 用后代选择器接管（.narrow .content 之类）；
另外三件事 CSS 做不到，必须在代码里做：
  ① 侧栏宽度 220 / 248；② 快捷功能 2 列 / 4 列（重建 Grid）；③ 隐藏页面说明与页脚。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    # ① 侧栏宽度要能切（220 / 248）
    ("        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        side.get_style_context().add_class('sidebar')\n"
     "        side.set_size_request(248, -1)",
     "        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)\n"
     "        side.get_style_context().add_class('sidebar')\n"
     "        side.set_size_request(248, -1)\n"
     "        self.sidebar_box = side        # 断点里会切成 220"),
    # ② 快捷功能：4 列规格存起来，窄屏时重建为 2 列
    ("        quick = Gtk.Grid(column_spacing=11, row_spacing=11)\n"
     "        quick.set_column_homogeneous(True)\n"
     "        for idx, (key, title, sub, icon) in enumerate((\n"
     "                ('token', '查看 Token', '访问凭证与连接信息', 'key'),\n"
     "                ('plugins', '管理插件', '安装、启用与配置扩展', 'puzzle'),\n"
     "                ('update', '检查更新', '获取最新的 dsh 与 Node', 'update'),\n"
     "                ('folder', '数据目录', '浏览配置与本地数据', 'folder'))):\n"
     "            quick.attach(self._quick_action(key, title, sub, icon), idx, 0, 1, 1)\n"
     "        section.pack_start(quick, False, False, 0)",
     "        self._quick_specs = (\n"
     "            ('token', '查看 Token', '访问凭证与连接信息', 'key'),\n"
     "            ('plugins', '管理插件', '安装、启用与配置扩展', 'puzzle'),\n"
     "            ('update', '检查更新', '获取最新的 dsh 与 Node', 'update'),\n"
     "            ('folder', '数据目录', '浏览配置与本地数据', 'folder'))\n"
     "        self.quick_grid = Gtk.Grid(column_spacing=11, row_spacing=11)\n"
     "        self.quick_grid.set_column_homogeneous(True)\n"
     "        self._quick_cols = 0\n"
     "        self._rebuild_quick_grid(4)\n"
     "        section.pack_start(self.quick_grid, False, False, 0)\n"
     "        self.quick_section = section"),
    # ③ 页面说明与页脚要能被断点隐藏
    ("        text.pack_start(self._label('管理服务、窗口与扩展，让实例始终保持最佳状态。',\n"
     "                                    'page-desc'), False, False, 0)",
     "        self.lbl_page_desc = self._label('管理服务、窗口与扩展，让实例始终保持最佳状态。',\n"
     "                                        'page-desc')\n"
     "        text.pack_start(self.lbl_page_desc, False, False, 0)"),
    ("        footer.set_hexpand(True)\n        page.pack_start(footer, False, False, 0)",
     "        footer.set_hexpand(True)\n        self.dash_footer = footer\n"
     "        page.pack_start(footer, False, False, 0)"),
    # 设置页同样要有说明标签的引用
    ("        text.pack_start(self._label('查看运行环境，管理外观与维护选项。', 'page-desc'),\n"
     "                        False, False, 0)",
     "        self.lbl_settings_desc = self._label('查看运行环境，管理外观与维护选项。', 'page-desc')\n"
     "        text.pack_start(self.lbl_settings_desc, False, False, 0)"),
    # ④ 概览右列宽度：宽屏 402、窄屏按 1.35:1 折算（下界 330）
    ("        control.set_size_request(402, -1)   # 高度交给 CSS（205 含 padding）",
     "        control.set_size_request(402, -1)   # 高度交给 CSS（205 含 padding）\n"
     "        self.control_card = control"),
]

METHODS = '''
    # ------------------------------------------------------------ 断点（DESIGN_SPEC §2.5）
    def _rebuild_quick_grid(self, cols):
        """快捷功能区：宽屏 4 列、窄屏 2 列（Gtk.Grid 没法自动回流，只能重建）。"""
        grid = getattr(self, 'quick_grid', None)
        if grid is None or getattr(self, '_quick_cols', None) == cols:
            return
        for child in grid.get_children():
            grid.remove(child)
        for idx, (key, title, sub, icon) in enumerate(getattr(self, '_quick_specs', ())):
            grid.attach(self._quick_action(key, title, sub, icon),
                        idx % cols, idx // cols, 1, 1)
        self._quick_cols = cols
        grid.show_all()

    def _apply_breakpoints(self, force=False):
        """窗口尺寸 → narrow / short 两个类，并处理 CSS 做不到的三件事。"""
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        if width <= 1 or height <= 1:
            return
        narrow = width <= 1280
        short = height <= 850
        if not force and (narrow, short) == getattr(self, '_bp', None):
            return
        self._bp = (narrow, short)

        ctx = self.get_style_context()
        for cls, on in (('narrow', narrow), ('short', short)):
            if on:
                ctx.add_class(cls)
            else:
                ctx.remove_class(cls)

        # ① 侧栏 220 / 248
        side = getattr(self, 'sidebar_box', None)
        if side is not None:
            side.set_size_request(220 if narrow else 248, -1)

        # ② 快捷功能 2 列 / 4 列
        self._rebuild_quick_grid(2 if narrow else 4)

        # ③ 概览右列：宽屏 402；窄屏按 1.35:1 折算，下界 330
        control = getattr(self, 'control_card', None)
        if control is not None:
            if narrow:
                content_w = max(0, width - (220 if narrow else 248) - 44)
                control.set_size_request(max(330, int(round(content_w / 2.35))), -1)
            else:
                control.set_size_request(402, -1)

        # ④ 隐藏页面说明 / 页脚（DESIGN_SPEC §2.5：高度 ≤850 时）
        for attr in ('lbl_page_desc', 'lbl_settings_desc'):
            lbl = getattr(self, attr, None)
            if lbl is not None:
                lbl.set_visible(not short)
        footer = getattr(self, 'dash_footer', None)
        if footer is not None:
            footer.set_visible(not short)

    def _on_size_allocate(self, _widget, alloc):
        self._apply_breakpoints()
'''

TAIL_CSS = """
/* ==========================================================================
 * 响应式断点（DESIGN_SPEC.md §2.5；设计稿是媒体查询，GTK 用窗口类 + 后代选择器）
 * ========================================================================== */

/* ≤1280px：侧栏 220 / 内容与顶栏 padding 22 / 快捷卡 70 高 / 卡片 padding 16 */
.narrow .content { padding: 22px; }
.narrow .topbar { padding: 0 22px; }
.narrow .quick-action { min-height: 42px; }      /* 70 - padding 26 - border 2 */
.narrow .quick-title { font-size: 10px; }
.narrow .instance-card, .narrow .control-card { padding: 16px; }
.narrow .control-sub { color: transparent; font-size: 1px; }  /* 设计稿 display:none 的等价处理 */
.narrow .log-card { margin-top: 16px; }
.narrow .brand-title { font-size: 11px; }

/* ≤850px：标题区收紧 / 卡片 190 / 区块间距收紧 / 页脚隐藏（代码里 set_visible） */
.short .content { padding-top: 18px; }
.short .page-heading { margin-bottom: 15px; }
.short .instance-card, .short .control-card { min-height: 152px; }   /* 190 - padding 36 - border 2 */
.short .quick-section { margin-top: 16px; }
.short .log-card { margin-top: 15px; }
.short .brand { margin-bottom: 18px; }
.short .runtime { margin-top: 10px; }

/* 焦点环（DESIGN_SPEC §8.3 / §10：3px 主色 25% + 2px 外偏移，不能被 outline:none 吃掉） */
button:focus, .btn:focus, .side-link:focus, .instance-item:focus,
.quick-action:focus, .icon-btn:focus, entry:focus, spinbutton:focus {
  outline: 3px solid alpha($(accent), .25);
  outline-offset: 2px;
}

/* 禁用态（DESIGN_SPEC §7.1：透明度 45~55%，无阴影、无位移） */
button:disabled, .btn:disabled, .side-link:disabled, .quick-action:disabled {
  opacity: .48;
  box-shadow: none;
}
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)

    if 'def _apply_breakpoints' not in s:
        anchor = '    def _build_topbar(self):'
        if anchor in s:
            s = s.replace(anchor, METHODS + '\n' + anchor, 1)
        else:
            missing.append('anchor _build_topbar')

    # 建完界面后挂上 size-allocate，并先跑一次
    if '_apply_breakpoints(force=True)' not in s:
        anchor2 = '        self.set_buttons_sensitive(False)'
        if anchor2 in s:
            s = s.replace(anchor2,
                          "        self.connect('size-allocate', self._on_size_allocate)\n"
                          "        GLib.timeout_add(300, lambda: (self._apply_breakpoints(force=True), False)[1])\n"
                          + anchor2, 1)
        else:
            missing.append('anchor set_buttons_sensitive')
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'
    c = io.open(CSS, encoding='utf-8').read()
    if '响应式断点（DESIGN_SPEC.md' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + TAIL_CSS)
        print('css breakpoints appended')
    print('gui patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
