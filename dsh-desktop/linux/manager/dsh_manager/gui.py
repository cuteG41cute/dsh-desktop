# -*- coding: utf-8 -*-
"""dsh-manager 图形界面（GTK3）。

一次装好、长期用：在同一个窗口里管多个 DSH 实例 ——
每个实例有自己的安装目录、Node、dsh 版本、数据目录和端口，互不干扰。
"""
import os
import subprocess
import sys
import threading

import gi

gi.require_version('Gtk', '3.0')
# Gdk 必须显式要 3.0：GTK4 也提供 Gdk 命名空间，谁先加载谁生效。
# 只 require Gtk 3.0 却直接 import Gdk 时，Gdk 会先按默认版本（4.0）加载，
# 随后 Gtk 3.0 就失败：Requiring namespace 'Gtk' version '3.0',
# but '4.0' is already loaded（实测踩过：1.0.5 起管理器因此启动即退出）。
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import plugins as plug  # noqa: E402
from .core import (DEFAULT_DSH, DEFAULT_NODE, MANAGER_LIB, MANAGER_VERSION,  # noqa: E402
                   FALLBACK_DSH_VERSIONS, FALLBACK_NODE_VERSIONS,
                   Manager, append_manager_log, config_dir, load_settings,
                   manager_log_path, port_free, read_manager_log, save_settings,
                   settings_path)

STATUS_TEXT = {
    'running': '运行中',
    'starting': '启动中',
    'external': '端口有服务（非本管理器）',
    'stopped': '已停止',
    'broken': '不完整（需修复）',
}

# 状态圆点颜色（与 style.css 里的徽标配色一致）
STATUS_DOT = {
    'running': '#2f7d4f',
    'stopped': '#a8761f',
    'broken': '#a8372c',
    'external': '#1f4e79',
    'starting': '#1f4e79',
}

CSS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'style.css')


def status_markup(status):
    """列表「状态」列的 Pango 标记：一个彩色圆点 + 文案。"""
    color = STATUS_DOT.get(status, '#7d838a')
    text = STATUS_TEXT.get(status, status or '')
    return '<span foreground="%s">●</span>  %s' % (color, GLib.markup_escape_text(text))


def load_css():
    """挂上企业简洁风主题。

    开关来源（优先级从高到低）：环境变量 DSH_MANAGER_NO_THEME=1 → settings.json 的 theme。
    加载失败只是回落默认皮肤，绝不影响功能。
    """
    if os.environ.get('DSH_MANAGER_NO_THEME') == '1':
        return False
    try:
        if not load_settings().get('theme', True):
            return False
    except Exception:
        pass
    try:
        provider = Gtk.CssProvider()
        provider.load_from_path(CSS_FILE)
    except Exception as exc:                     # 文件缺失 / GTK 语法不被支持
        sys.stderr.write('[dsh-manager] 主题未加载（继续用默认皮肤）：%s\n' % exc)
        return False
    screen = Gdk.Screen.get_default()
    if screen is None:
        return False
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    return True


class VersionPicker(Gtk.MenuButton):
    """可滚动的版本选择器。

    GTK 自带的 Gtk.ComboBox 用的是菜单式下拉，列表一长就滚不动（只能滚一下），
    这里换成 Popover + ScrolledWindow + ListBox：给死最小/最大高度，永远能滚，
    并且可以放 'latest' 这种"由管理器去解析"的伪版本。
    """

    def __init__(self, options=None, value=None, width_chars=24):
        Gtk.MenuButton.__init__(self)
        self._value = ''
        self._label = Gtk.Label(xalign=0.0)
        self._label.set_width_chars(width_chars)
        self._label.set_ellipsize(3)              # 末尾省略号
        self.add(self._label)                     # GTK3 的 MenuButton 是 Gtk.Bin
        self.set_valign(Gtk.Align.CENTER)
        self.set_tooltip_text('点击选择版本（列表可滚动）')

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(180)
        sw.set_max_content_height(300)
        sw.set_propagate_natural_height(True)
        sw.set_size_request(240, -1)
        self._list = Gtk.ListBox()
        self._list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list.get_style_context().add_class('version-list')
        self._list.connect('row-activated', self._on_row)
        sw.add(self._list)

        pop = Gtk.Popover.new(self)
        pop.add(sw)
        self.set_popover(pop)

        self.set_options(options or [])
        if value:
            self.set_value(value)

    def set_options(self, options):
        for child in self._list.get_children():
            self._list.remove(child)
        for opt in options:
            row = Gtk.ListBoxRow()
            row.value = opt
            lbl = Gtk.Label(label=opt, xalign=0.0)
            lbl.set_margin_top(6)
            lbl.set_margin_bottom(6)
            lbl.set_margin_start(10)
            lbl.set_margin_end(10)
            row.add(lbl)
            self._list.add(row)
        self._list.show_all()
        if self._value in options:
            self.set_value(self._value)
        elif options:
            self.set_value(options[0])
        else:
            self.set_value('')

    def _on_row(self, _lb, row):
        self.set_value(getattr(row, 'value', ''))
        pop = self.get_popover()
        if pop is not None:
            pop.popdown()

    def set_value(self, value):
        self._value = value or ''
        self._label.set_text(self._value or '—')

    def get_value(self):
        return self._value


def make_pulse_bar():
    """不确定进度条（脉冲式，观感类似 Win7 的"滚动光条"）。"""
    bar = Gtk.ProgressBar()
    bar.set_pulse_step(0.06)
    return bar


def pulse_until(bar, state):
    """在 state['done'] 之前持续脉冲；返回 False 让它自己停。"""
    def tick():
        if state.get('done'):
            return False
        try:
            bar.pulse()
        except Exception:
            return False
        return True
    GLib.timeout_add(110, tick)


class ManagerWindow(Gtk.Window):
    def __init__(self, manager=None):
        Gtk.Window.__init__(self, title='DeepSeek Harness 管理器 %s' % MANAGER_VERSION)
        self.manager = manager or Manager()
        self.set_default_size(1060, 720)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.selected = None
        self.busy = False
        self.win_width = 1060      # _fit_to_screen 会按屏幕修正
        self.win_height = 720
        self.settings = load_settings()
        # 主题只是外观：想回到 GTK 默认皮肤，设 DSH_MANAGER_NO_THEME=1 或删掉 style.css
        self.theme_loaded = load_css()
        self._fit_to_screen()
        self._build()
        self.refresh()
        GLib.timeout_add(400, self._drain_log)
        GLib.timeout_add(4000, self._tick)

    def _fit_to_screen(self):
        """把「初始尺寸」缩到屏幕工作区内。

        踩过：默认 1060×720 的窗口放在 1280×720 的小屏上，标题栏 + 任务栏一挤，
        窗口底部就跑到屏幕外了 —— 最后一组按钮和日志框**根本点不到也拉不上来**。

        注意：这里只决定**打开时多大**，不设窗口最小尺寸 —— 想缩多小由用户自己拖，
        极限由内容自己决定（上部是滚动区、日志卡只有 64px 底）。
        """
        try:
            display = Gdk.Display.get_default()
            if display is None:
                return
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            area = monitor.get_workarea()
            width = max(760, min(1060, area.width - 60))
            height = max(520, min(720, area.height - 60))
            self.win_width = width
            self.win_height = height
            self.set_default_size(width, height)
            self.resize(width, height)
        except Exception:
            pass

    # ------------------------------------------------------------ 界面
    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)

        # ---------- 顶栏 ----------
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.props.title = 'DeepSeek Harness 管理器'
        hb.props.subtitle = '多实例 · 多版本 · 安装 / 更新 / 修复 / 卸载'
        btn_new = Gtk.Button(label='＋ 新建实例')
        btn_new.get_style_context().add_class('primary')
        btn_new.connect('clicked', self.on_new)
        hb.pack_start(btn_new)
        pill = Gtk.Label(label='v%s' % MANAGER_VERSION)
        pill.get_style_context().add_class('pill')
        hb.pack_end(pill)
        btn_refresh = Gtk.Button.new_from_icon_name('view-refresh-symbolic', Gtk.IconSize.BUTTON)
        btn_refresh.set_tooltip_text('刷新')
        btn_refresh.connect('clicked', lambda *a: self.refresh())
        hb.pack_end(btn_refresh)
        btn_settings = Gtk.Button.new_from_icon_name('emblem-system-symbolic', Gtk.IconSize.BUTTON)
        btn_settings.set_tooltip_text('管理器设置（版本 / 主题 / 日志 / 卸载）')
        btn_settings.connect('clicked', self.on_settings)
        hb.pack_end(btn_settings)
        self.set_titlebar(hb)

        # 忙碌指示条（安装/更新/修复期间）：脉冲进度 + 一行说明
        self.busy_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.busy_box.set_border_width(10)
        self.busy_lbl = Gtk.Label(xalign=0)
        self.busy_lbl.get_style_context().add_class('dim-label')
        self.busy_bar = make_pulse_bar()
        self.busy_box.pack_start(self.busy_lbl, False, False, 0)
        self.busy_box.pack_start(self.busy_bar, False, False, 0)
        self.busy_box.set_no_show_all(True)
        root.pack_start(self.busy_box, False, False, 0)
        self.busy_box.hide()
        self._busy_pulse_id = None

        # ---------- 中部：左列表 + 右详情 ----------
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        # 左列表按窗口宽度取 45%（小屏上写死 600 会把右侧按钮区挤没）
        paned.set_position(max(320, min(560, int(getattr(self, "win_width", 1060) * 0.45))))
        root.pack_start(paned, True, True, 0)

        # 左：实例列表（卡片 + 细线表格）
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left.set_border_width(14)
        list_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_card.get_style_context().add_class('card')
        self.store = Gtk.ListStore(str, str, str, str, str, str)   # label, prefix, dsh, node, port, status(markup)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(True)
        for title, width, idx, prop in (('名称', 170, 0, 'text'), ('dsh', 96, 2, 'text'),
                                        ('node', 84, 3, 'text'), ('端口', 58, 4, 'text'),
                                        ('状态', 128, 5, 'markup')):
            renderer = Gtk.CellRendererText()
            renderer.set_property('ellipsize', 3)      # END
            col = Gtk.TreeViewColumn(title, renderer)
            col.add_attribute(renderer, prop, idx)
            col.set_resizable(True)
            col.set_min_width(width)
            self.tree.append_column(col)
        self.tree.connect('cursor-changed', self.on_select)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class('panel')
        scroll.add(self.tree)
        list_card.pack_start(scroll, True, True, 0)
        left.pack_start(list_card, True, True, 0)
        self.lbl_prefix = Gtk.Label(label='', xalign=0)
        self.lbl_prefix.set_ellipsize(3)      # END
        self.lbl_prefix.get_style_context().add_class('dim-label')
        left.pack_start(self.lbl_prefix, False, False, 0)
        paned.pack1(left, True, False)

        # 右：上部（标题 / 信息卡 / 分组按钮，可滚动）+ 下部（日志，有最小高度、可拉动）
        # 只有一块「长东西」时也必须能滚到底：小屏上按钮组会把日志挤出窗口外（踩过）。
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        right.set_border_width(14)

        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        top_scroll = Gtk.ScrolledWindow()
        top_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        top_scroll.set_shadow_type(Gtk.ShadowType.NONE)
        top_scroll.add(top)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.lbl_title = Gtk.Label(label='选择左侧的实例', xalign=0)
        self.lbl_title.get_style_context().add_class('inst-title')
        self.lbl_badge = Gtk.Label(label='')
        self.lbl_badge.get_style_context().add_class('badge')
        self.lbl_badge.set_no_show_all(True)
        title_row.pack_start(self.lbl_title, False, False, 0)
        title_row.pack_start(self.lbl_badge, False, False, 0)
        top.pack_start(title_row, False, False, 0)

        self.info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.info_card.get_style_context().add_class('card')
        self.lbl_info = Gtk.Label(label='', xalign=0, wrap=True)
        self.lbl_info.set_selectable(True)
        self.lbl_info.get_style_context().add_class('info-val')
        self.info_card.pack_start(self.lbl_info, False, False, 0)
        top.pack_start(self.info_card, False, False, 0)

        # 按钮按「服务 / 窗口 / 版本 / 插件 / 其他」分组，危险操作单独标红
        self.buttons = {}

        def make_group(title, items):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            label = Gtk.Label(label=title, xalign=0)
            label.get_style_context().add_class('group-label')
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            for key, text, cls in items:
                btn = Gtk.Button(label=text)
                if cls:
                    btn.get_style_context().add_class(cls)
                btn.connect('clicked', getattr(self, 'on_' + key))
                row.pack_start(btn, False, False, 0)
                self.buttons[key] = btn
            box.pack_start(label, False, False, 0)
            box.pack_start(row, False, False, 0)
            return box

        top.pack_start(make_group('服务', (
            ('start', '启动服务', 'primary'), ('stop', '停止服务', None),
            ('open', '打开窗口', None))), False, False, 0)
        # 窗口本身也可能"活着但画面坏了"（软件渲染下上半截空白），唤起修不好，
        # 需要能重开一个：重建窗口 = 杀掉窗口进程 + 清锁 + 重新起（不动服务/会话）。
        top.pack_start(make_group('窗口', (
            ('reload', '重载页面', None), ('rebuild', '重建窗口', None),
            ('token', '查看 Token', None))),
            False, False, 0)
        top.pack_start(make_group('版本', (
            ('update', '更新版本', None), ('repair', '修复', None))), False, False, 0)
        top.pack_start(make_group('插件', (('plugins', '管理插件…', None),)),
                       False, False, 0)
        top.pack_start(make_group('其他', (
            ('folder', '在文件管理器中显示', None), ('uninstall', '卸载', 'danger'))),
            False, False, 0)

        log_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        log_card.get_style_context().add_class('card')
        log_card.set_size_request(-1, 120)      # 日志至少留 120px（约 4~5 行），缩窗口时不会被压没
        log_head = Gtk.Label(label='日志', xalign=0)
        log_head.get_style_context().add_class('card-title')
        log_card.pack_start(log_head, False, False, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.get_style_context().add_class('panel')
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_buf = self.log_view.get_buffer()
        sw.add(self.log_view)
        log_card.pack_start(sw, True, True, 0)

        vpaned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        # 日志高度按**窗口高度的百分比**走（默认 38%），窗口变大变小它跟着变；
        # 拖动分隔条会覆盖这个比例并被记住（不再是写死的像素值）。
        self._log_ratio = 0.38
        vpaned.set_position(
            max(120, int(getattr(self, 'win_height', 720) * (1.0 - self._log_ratio))))
        vpaned.pack1(top_scroll, True, False)  # 窗口变矮时上部自己滚动，不再挤掉日志
        vpaned.pack2(log_card, True, True)     # 日志也参与分配：窗口变高时它一起变高

        def apply_ratio(*_a):
            total = vpaned.get_allocated_height() or self.get_allocated_height()
            if not total or total < 200:
                return False
            log_h = max(90, int(total * self._log_ratio))
            pos = max(80, total - log_h)
            if abs(vpaned.get_position() - pos) > 6:
                vpaned.set_position(pos)
            return False

        def remember_ratio(*_a):
            total = vpaned.get_allocated_height() or self.get_allocated_height()
            if not total:
                return
            ratio = 1.0 - (vpaned.get_position() / float(total))
            self._log_ratio = max(0.12, min(0.85, ratio))

        vpaned.connect('notify::position', remember_ratio)
        # 窗口尺寸变化时重算（只移动几个像素就跳过的判断在里面，不会打架）
        self.connect('configure-event', lambda *a: (apply_ratio(), False)[1])
        GLib.timeout_add(400, lambda: (apply_ratio(), False)[1])

        right.pack_start(vpaned, True, True, 0)

        paned.pack2(right, True, False)
        self.set_buttons_sensitive(False)

    def set_buttons_sensitive(self, has_selection):
        for key, btn in self.buttons.items():
            btn.set_sensitive(has_selection and not self.busy)
        if self.selected is not None:
            self.buttons['start'].set_sensitive(not self.busy and self.selected.status() == 'stopped')
            self.buttons['stop'].set_sensitive(not self.busy and bool(self.selected.running_pid()))

    def append_log(self, line, persist=True):
        text = line.rstrip('\n')
        end = self.log_buf.get_end_iter()
        self.log_buf.insert(end, text + '\n')
        mark = self.log_buf.create_mark(None, self.log_buf.get_end_iter(), False)
        self.log_view.scroll_mark_onscreen(mark)
        if persist:
            append_manager_log(text)      # 同时落盘，供「设置 → 管理器日志」查看
        # 面板只留最近 N 行，避免长时间运行后卡顿
        limit = int(self.settings.get('logLines') or 800)
        count = self.log_buf.get_line_count()
        if count > limit + 200:
            start = self.log_buf.get_start_iter()
            cut = self.log_buf.get_iter_at_line(count - limit)
            self.log_buf.delete(start, cut)

    def _drain_log(self):
        for line in self.manager.take_log():
            self.append_log(line)
        return True

    def _tick(self):
        # 只刷新状态列（避免每次重建整张表）
        if self.busy:
            return True
        instances = self.manager.list_instances()
        for row in self.store:
            for inst in instances:
                if inst.prefix == row[1]:
                    row[5] = status_markup(inst.status())
        if self.selected is not None:
            self._fill_details(self.selected)
        return True

    # ------------------------------------------------------------ 列表/详情
    def refresh(self):
        keep = self.selected.prefix if self.selected is not None else None
        self.store.clear()
        instances = self.manager.list_instances()
        target = None
        for inst in instances:
            it = self.store.append([inst.label, inst.prefix, inst.dsh_version or '-',
                                    inst.node_version or '-', str(inst.port),
                                    status_markup(inst.status())])
            if keep and inst.prefix == keep:
                target = it
        if target is not None:
            # 刷新后保持选中（否则每次装/改完都要重新点一次）
            path = self.store.get_path(target)
            self.tree.get_selection().select_path(path)
        if not instances:
            self.lbl_prefix.set_text('还没有实例：点左上角「＋ 新建实例」。默认会装到 %s' % self.manager.root)
            self.set_buttons_sensitive(False)
        else:
            self.lbl_prefix.set_text('实例根目录：%s' % self.manager.root)

    def on_select(self, tree):
        model, it = tree.get_selection().get_selected()
        if it is None:
            self.selected = None
            self.set_buttons_sensitive(False)
            return
        prefix = model[it][1]
        self.selected = self.manager.instance_at(prefix)
        self._fill_details(self.selected)
        self.set_buttons_sensitive(True)

    def _fill_details(self, inst):
        status = inst.status()
        pid = inst.running_pid()
        self.lbl_title.set_text(inst.label)

        # 状态徽标
        ctx = self.lbl_badge.get_style_context()
        for cls in ('running', 'stopped', 'broken', 'external', 'starting'):
            ctx.remove_class(cls)
        ctx.add_class(status if status in STATUS_DOT else 'external')
        self.lbl_badge.set_text(STATUS_TEXT.get(status, status))
        self.lbl_badge.show()

        esc = GLib.markup_escape_text
        rows = [
            ('安装位置', esc(inst.prefix)),
            ('版本', 'dsh %s · Node %s · 端口 %d'
             % (esc(inst.dsh_version or '?'), esc(inst.node_version or '?'), inst.port)),
            ('数据目录', esc(inst.dsh_home)),
        ]
        if pid:
            rows.append(('进程', 'PID %d' % pid))
        info = '\n'.join('<span foreground="#7d838a">%s</span>  %s' % (k, v) for k, v in rows)
        self.lbl_info.set_markup(info)

    # ------------------------------------------------------------ 动作（线程里跑）
    def _busy_show(self, text):
        try:
            self.busy_lbl.set_text(text)
            self.busy_box.show_all()
        except Exception:
            return
        if self._busy_pulse_id is None:
            self._busy_pulse_id = GLib.timeout_add(110, self._busy_pulse)

    def _busy_pulse(self):
        if not self.busy:
            self._busy_pulse_id = None
            return False
        try:
            self.busy_bar.pulse()
        except Exception:
            self._busy_pulse_id = None
            return False
        return True

    def _busy_hide(self):
        self._busy_pulse_id = None
        try:
            self.busy_box.hide()
        except Exception:
            pass

    def _run_async(self, title, fn, on_done=None):
        if self.busy:
            return
        self.busy = True
        self.set_buttons_sensitive(True)
        self.append_log('—— %s ——' % title)
        self.set_title('DeepSeek Harness 管理器 · %s…' % title)
        self._busy_show('%s…（耗时的部分在后台跑，界面不会卡死）' % title)

        def worker():
            try:
                result = fn()
            except Exception as exc:          # 兜底：任何异常都别把界面卡死
                result = (False, '异常：%s' % exc, None)
            GLib.idle_add(self._finish, title, result, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, title, result, on_done):
        self.busy = False
        self._busy_hide()
        ok, msg = result[0], result[1]
        self.append_log(('✔ ' if ok else '✘ ') + str(msg))
        self.set_title('DeepSeek Harness 管理器 %s' % MANAGER_VERSION)
        self.refresh()
        if self.selected is not None:
            self._fill_details(self.selected)
        self.set_buttons_sensitive(self.selected is not None)
        if on_done:
            on_done(ok, result)
        return False

    def _confirm(self, text, secondary=None):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.OK_CANCEL, text=text)
        if secondary:
            dlg.format_secondary_text(secondary)
        resp = dlg.run()
        dlg.destroy()
        return resp == Gtk.ResponseType.OK

    # ---- 新建 ----
    def on_new(self, *_):
        dlg = Gtk.Dialog(title='新建实例', transient_for=self, modal=True)
        dlg.add_buttons('取消', Gtk.ResponseType.CANCEL, '安装', Gtk.ResponseType.OK)
        dlg.set_default_size(560, 320)
        grid = Gtk.Grid(column_spacing=8, row_spacing=10, border_width=12)
        dlg.get_content_area().add(grid)

        idx = 1
        for inst in self.manager.list_instances():
            try:
                idx = max(idx, int(os.path.basename(inst.prefix).rsplit('-', 1)[-1]) + 1)
            except ValueError:
                pass
        default_prefix = os.path.join(self.manager.root, 'deepseek-harness-%d' % idx)

        ent_prefix = Gtk.Entry(text=default_prefix)
        ent_label = Gtk.Entry(text=os.path.basename(default_prefix))
        ent_port = Gtk.SpinButton.new_with_range(1024, 65535, 1)
        ent_port.set_value(self.manager.next_port())

        # 版本选择：先摆出 latest + 内置清单（对话框立刻可用），联网列表在后台拉，
        # 拉回来再塞进去；右侧再给一个输入框，列表不准/拉不到时可以直接手打版本号。
        picker_dsh = VersionPicker(['latest'] + list(FALLBACK_DSH_VERSIONS), value='latest')
        picker_node = VersionPicker(['latest'] + list(FALLBACK_NODE_VERSIONS), value='latest')
        ent_dsh_manual = Gtk.Entry()
        ent_dsh_manual.set_placeholder_text('或手动输入 dsh 版本，如 0.2.1-rc.5')
        ent_dsh_manual.set_width_chars(22)
        ent_node_manual = Gtk.Entry()
        ent_node_manual.set_placeholder_text('或手动输入 Node 版本，如 26.13.0')
        ent_node_manual.set_width_chars(22)
        box_dsh = Gtk.Box(spacing=6)
        box_dsh.pack_start(picker_dsh, False, False, 0)
        box_dsh.pack_start(ent_dsh_manual, True, True, 0)
        box_node = Gtk.Box(spacing=6)
        box_node.pack_start(picker_node, False, False, 0)
        box_node.pack_start(ent_node_manual, True, True, 0)

        ver_state = {'done': False}
        ver_bar = make_pulse_bar()
        ver_lbl = Gtk.Label(xalign=0, wrap=True)
        ver_lbl.set_text('正在联网获取可用版本（可以先直接用 latest 安装）…')
        ver_lbl.get_style_context().add_class('dim-label')
        box_ver = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box_ver.pack_start(ver_lbl, False, False, 0)
        box_ver.pack_start(ver_bar, False, False, 0)
        pulse_until(ver_bar, ver_state)
        dlg.connect('destroy', lambda *a: ver_state.__setitem__('done', True))

        def fetch_versions():
            # 每一项单独兜底：一项失败不能把其它几项的结果一起扔掉
            # （踩过：拉完整 registry 文档超时 → 列表只剩内置一项，用户"选不了版本"）
            dsh_list, node_list = [], []
            latest_dsh, latest_node = DEFAULT_DSH, DEFAULT_NODE
            problems = []
            try:
                dsh_list = self.manager.available_dsh_versions(14) or []
            except Exception as exc:
                problems.append('dsh 版本列表：%s' % exc)
            try:
                node_list = self.manager.available_node_versions() or []
            except Exception as exc:
                problems.append('Node 版本列表：%s' % exc)
            try:
                latest_dsh = self.manager.latest_dsh_version() or DEFAULT_DSH
            except Exception:
                pass
            try:
                latest_node = self.manager.latest_node_version() or DEFAULT_NODE
            except Exception:
                pass

            def apply():
                ver_state['done'] = True
                try:
                    ver_bar.hide()
                    if dsh_list:
                        head = '版本列表已就绪：latest = dsh %s / Node %s' % (latest_dsh, latest_node)
                    else:
                        head = ('联网获取版本列表失败，下面用的是内置清单（latest = dsh %s / Node %s）；'
                                '也可以直接在右侧手动输入版本号' % (latest_dsh, latest_node))
                    if problems:
                        head += '\n' + '；'.join(problems[:2])
                    ver_lbl.set_text(head)
                    picker_dsh.set_options(['latest'] + [v for v in dsh_list if v != 'latest'])
                    picker_node.set_options(['latest'] + [v for v in node_list if v != 'latest'])
                except Exception:
                    pass
                return False
            GLib.idle_add(apply)

        threading.Thread(target=fetch_versions, daemon=True).start()

        def browse(*_):
            chooser = Gtk.FileChooserDialog(title='选择安装目录', transient_for=dlg,
                                            action=Gtk.FileChooserAction.SELECT_FOLDER)
            chooser.add_buttons('取消', Gtk.ResponseType.CANCEL, '选择', Gtk.ResponseType.OK)
            chooser.set_current_folder(os.path.dirname(ent_prefix.get_text()) or self.manager.root)
            if chooser.run() == Gtk.ResponseType.OK:
                ent_prefix.set_text(os.path.join(chooser.get_filename(),
                                                 os.path.basename(ent_prefix.get_text()) or 'deepseek-harness'))
            chooser.destroy()

        btn_browse = Gtk.Button(label='浏览…')
        btn_browse.connect('clicked', browse)
        box_prefix = Gtk.Box(spacing=6)
        box_prefix.pack_start(ent_prefix, True, True, 0)
        box_prefix.pack_start(btn_browse, False, False, 0)

        rows = [('安装目录', box_prefix), ('显示名称', ent_label), ('端口', ent_port),
                ('dsh 版本', box_dsh), ('Node 版本', box_node)]
        for r, (label, widget) in enumerate(rows):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, r, 1, 1)
            grid.attach(widget, 1, r, 1, 1)
        grid.attach(box_ver, 0, len(rows), 2, 1)
        hint = Gtk.Label(xalign=0, wrap=True)
        hint.set_text('提示：latest = 最新的非 alpha 版本（由管理器联网解析）；每个实例自带 Node 与 dsh，'
                      '装在所选目录里，数据目录是该目录下的 dsh-home，不会动 ~/.dsh。'
                      '安装需要联网（下载 Node 与 npm 包）。')
        hint.get_style_context().add_class('dim-label')
        grid.attach(hint, 0, len(rows) + 1, 2, 1)
        dlg.show_all()
        resp = dlg.run()
        if resp != Gtk.ResponseType.OK:
            ver_state['done'] = True
            dlg.destroy()
            return
        prefix = ent_prefix.get_text().strip()
        label = ent_label.get_text().strip() or os.path.basename(prefix)
        port = int(ent_port.get_value())
        dsh = ent_dsh_manual.get_text().strip() or picker_dsh.get_value() or 'latest'
        node = ent_node_manual.get_text().strip() or picker_node.get_value() or 'latest'
        ver_state['done'] = True
        dlg.destroy()
        if os.path.exists(prefix) and not os.path.isdir(prefix):
            self.append_log('✘ 目标路径已存在且不是目录：%s' % prefix)
            return
        self._run_async('安装 %s' % os.path.basename(prefix),
                        lambda: self.manager.install(prefix, dsh, node, port, label))

    # ------------------------------------------------------------ 管理器自身的设置
    def _copy(self, text):
        try:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text, -1)
            clipboard.store()
            return True
        except Exception:
            return False

    def _dialog_size(self, width, height):
        """对话框尺寸：**按管理器窗口的百分比**给，而不是死的像素值。

        踩过两件事：
          1. 日志窗口里用 Box.add() 把孩子塞进去 —— 那等价于 pack_start(False, False)，不伸展，
             于是 TextView 只有两行高，剩下半个对话框全空着；
          2. 死写 780×520 在小屏上又超出屏幕。
        这里按"窗口的 72% 宽、80% 高"取，并夹在屏幕工作区内。
        """
        try:
            win_w = self.get_allocated_width() or 1060
            win_h = self.get_allocated_height() or 720
        except Exception:
            win_w, win_h = 1060, 720
        want_w = max(520, int(win_w * 0.72))
        want_h = max(320, int(win_h * 0.80))
        try:
            display = Gdk.Display.get_default()
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            area = monitor.get_workarea()
            want_w = min(want_w, max(420, area.width - 80))
            want_h = min(want_h, max(300, area.height - 80))
        except Exception:
            pass
        return min(width or want_w, want_w), min(height or want_h, want_h)

    def _text_dialog(self, title, text, width=None, height=None):
        dlg = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dlg.add_buttons('关闭', Gtk.ResponseType.CLOSE)
        w, h = self._dialog_size(width, height)
        dlg.set_default_size(w, h)
        area = dlg.get_content_area()
        area.set_border_width(14)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.get_style_context().add_class('panel')
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text(text)
        sw.add(view)
        # 必须 pack_start(..., True, True)：Gtk.Box.add() 等价于不伸展，
        # 会让文字区只剩两行高（用户实测："日志只显示两行"）。
        area.pack_start(sw, True, True, 0)
        dlg.show_all()
        dlg.run()
        dlg.destroy()

    def _section(self, title):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class('card')
        head = Gtk.Label(label=title, xalign=0)
        head.get_style_context().add_class('card-title')
        card.pack_start(head, False, False, 0)
        return card

    def _commands(self):
        ver = MANAGER_VERSION
        return {
            'repair': ('重装 / 修复管理器',
                       'sudo apt install --reinstall ./dsh-manager_%s_all.deb\n'
                       'sudo apt --fix-broken install' % ver),
            'uninstall': ('卸载管理器',
                          '# 只删管理器本体，实例目录（~/.local/opt/...）与数据都保留\n'
                          'sudo apt remove dsh-manager\n\n'
                          '# 想连配置一起清掉（实例仍然保留）\n'
                          'rm -rf ~/.config/dsh-manager'),
        }

    def on_settings(self, *_):
        dlg = Gtk.Dialog(title='管理器设置', transient_for=self, modal=True)
        dlg.add_buttons('关闭', Gtk.ResponseType.CLOSE)
        dlg.set_default_size(760, 620)
        area = dlg.get_content_area()
        area.set_border_width(16)
        area.set_spacing(12)

        # ---- 版本与路径 ----
        info = self._section('管理器')
        grid = Gtk.Grid(column_spacing=16, row_spacing=6)
        gtk_ver = '%d.%d.%d' % (Gtk.get_major_version(), Gtk.get_minor_version(),
                                Gtk.get_micro_version())
        rows = (
            ('版本', 'v%s' % MANAGER_VERSION),
            ('程序目录', MANAGER_LIB),
            ('配置目录', config_dir()),
            ('管理器日志', manager_log_path()),
            ('运行环境', 'Python %s · GTK %s' % (sys.version.split()[0], gtk_ver)),
            ('实例根目录', self.manager.root),
        )
        for r, (key, value) in enumerate(rows):
            k = Gtk.Label(label=key, xalign=0)
            k.get_style_context().add_class('group-label')
            v = Gtk.Label(label=value, xalign=0)
            v.get_style_context().add_class('info-val')
            v.set_selectable(True)
            v.set_ellipsize(3)          # END
            grid.attach(k, 0, r, 1, 1)
            grid.attach(v, 1, r, 1, 1)
        info.pack_start(grid, False, False, 0)
        area.pack_start(info, False, False, 0)

        # ---- 外观 ----
        look = self._section('外观')
        chk = Gtk.CheckButton(label='使用企业简洁风主题（重启管理器后生效）')
        chk.set_active(bool(self.settings.get('theme', True)))
        look.pack_start(chk, False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label(label='日志面板保留行数', xalign=0)
        lbl.get_style_context().add_class('info-val')
        spin = Gtk.SpinButton.new_with_range(200, 5000, 100)
        spin.set_value(int(self.settings.get('logLines') or 800))
        row.pack_start(lbl, False, False, 0)
        row.pack_start(spin, False, False, 0)
        look.pack_start(row, False, False, 0)

        def apply_look(*_):
            values = {'theme': bool(chk.get_active()), 'logLines': int(spin.get_value())}
            ok = save_settings(values)
            self.settings.update(values)
            self.append_log(('✔ 设置已保存%s' % ('（主题改动重启后生效）' if True else ''))
                            if ok else '✘ 保存设置失败（配置目录不可写？）')

        btn_save = Gtk.Button(label='保存外观设置')
        btn_save.get_style_context().add_class('primary')
        btn_save.connect('clicked', apply_look)
        look.pack_start(btn_save, False, False, 0)
        area.pack_start(look, False, False, 0)

        # ---- 维护 ----
        maint = self._section('维护')
        mrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        def view_log(*_):
            lines = read_manager_log(400)
            head = ['—— 管理器日志 ——',
                    '文件：%s' % manager_log_path(),
                    '行数：%d（这里显示最后 400 行；主窗口下方是本次运行的实时日志）' % len(lines),
                    '']
            body = lines if lines else ['（文件里还没有日志）']
            self._text_dialog('管理器日志', '\n'.join(head + body))

        def copy_diag(*_):
            parts = ['DeepSeek Harness 管理器 v%s' % MANAGER_VERSION,
                     '程序目录: %s' % MANAGER_LIB,
                     '配置目录: %s' % config_dir(),
                     '运行环境: Python %s · GTK %s' % (sys.version.split()[0], gtk_ver),
                     '主题: %s（style.css）' % ('已启用' if self.theme_loaded else '未启用'),
                     '实例根目录: %s' % self.manager.root,
                     '', '实例:']
            try:
                for inst in self.manager.list_instances():
                    parts.append('  - %s  dsh %s  node %s  端口 %d  %s  %s'
                                 % (inst.label, inst.dsh_version or '?',
                                    inst.node_version or '?', inst.port,
                                    STATUS_TEXT.get(inst.status(), inst.status()),
                                    inst.prefix))
            except Exception as exc:
                parts.append('  （读取失败：%s）' % exc)
            parts += ['', '最近日志:'] + ['  ' + ln for ln in read_manager_log(40)]
            ok = self._copy('\n'.join(parts))
            self.append_log('✔ 诊断信息已复制到剪贴板' if ok else '✘ 复制失败（没有剪贴板？）')

        def show_cmd(kind):
            def handler(*_):
                title, cmd = self._commands()[kind]
                self._text_dialog(title, cmd + '\n\n（在终端里执行；管理器运行中无法卸载自己）', 720, 320)
            return handler

        for label, handler in (('查看管理器日志', view_log),
                               ('复制诊断信息', copy_diag),
                               ('修复 / 重装…', show_cmd('repair')),
                               ('卸载…', show_cmd('uninstall'))):
            btn = Gtk.Button(label=label)
            btn.connect('clicked', handler)
            mrow.pack_start(btn, False, False, 0)
        maint.pack_start(mrow, False, False, 0)
        note = Gtk.Label(xalign=0, wrap=True)
        note.set_text('管理器不会删除你的实例目录：卸载只移除 /usr 里的程序，'
                      '每个实例仍在你创建时选定的目录里（数据目录是该实例的 dsh-home）。')
        note.get_style_context().add_class('dim-label')
        maint.pack_start(note, False, False, 0)
        area.pack_start(maint, False, False, 0)

        dlg.show_all()
        dlg.run()
        dlg.destroy()

    # ---- 选择校验 ----
    def _need(self, what='实例'):
        if self.selected is None:
            self.append_log('请先在左侧选择一个实例')
            return None
        return self.selected

    # ---- 启停/打开 ----
    def on_start(self, *_):
        inst = self._need()
        if not inst:
            return
        self._run_async('启动 %s' % inst.label, lambda: (inst.start()))

    def on_stop(self, *_):
        inst = self._need()
        if not inst:
            return
        self._run_async('停止 %s' % inst.label, lambda: (inst.stop()))

    def on_open(self, *_):
        inst = self._need()
        if not inst:
            return

        def job():
            ok, msg = inst.start()
            if not ok:
                return ok, msg
            # 走管理器这一层：先把实例里的窗口程序对齐到本包版本，
            # 再交给实例的 open_window（唤起已有窗口 / 清理旧现场 / 强制重试）
            return self.manager.open_window(inst.prefix)
        self._run_async('打开窗口 %s' % inst.label, job)

    def on_reload(self, *_):
        """让窗口重新加载页面（页面脚本把布局搞坏时最快的动作）。"""
        inst = self._need()
        if not inst:
            return
        pid = inst.window_alive()
        if not pid:
            self.append_log('✘ 没有正在运行的窗口；先点「打开窗口」。')
            return

        def job():
            if inst.reload_page():
                return True, '已让窗口重新加载页面（PID %s）' % pid
            return False, ('窗口没响应 reload 命令（PID %s，可能是旧版窗口）——'
                           '请点「重建窗口」' % pid)
        self._run_async('重载页面 %s' % inst.label, job)

    def on_rebuild(self, *_):
        """重建窗口：杀掉窗口进程、清锁、重新起一个（服务与会话都不动）。"""
        inst = self._need()
        if not inst:
            return

        def job():
            ok, msg = inst.start()
            if not ok:
                return ok, msg
            return self.manager.open_window(inst.prefix, rebuild=True)
        self._run_async('重建窗口 %s' % inst.label, job)

    def on_folder(self, *_):
        inst = self._need()
        if not inst:
            return
        import subprocess
        try:
            subprocess.Popen(['xdg-open', inst.prefix])
        except Exception as exc:
            self.append_log('✘ 打开目录失败：%s' % exc)

    # ---- 查看 WebUI 的 Token（在浏览器里打开 dsh 用）----
    def _show_secret(self, title, value, source='', status=''):
        """把 token 这类敏感值只展示在界面上：**不落盘**、顺手放进剪贴板。"""
        self.append_log('—— %s ——' % title, persist=False)
        self.append_log(value, persist=False)
        if status:
            self.append_log('验证：%s' % status, persist=False)
        if source:
            self.append_log('来源：%s' % source, persist=False)
        try:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(value, -1)
            self.append_log('已复制到剪贴板，可直接粘到浏览器地址栏。', persist=False)
        except Exception as exc:
            self.append_log('（复制到剪贴板失败：%s；可以选中上面那行手动复制）' % exc, persist=False)
        self.append_log('提示：这条地址等价于密码；打开一次后同一浏览器就能直接用裸地址。',
                        persist=False)

    def on_token(self, *_):
        """查看当前实例的 WebUI 入口地址（带 token），按用户要求显示在下方日志框。"""
        inst = self._need()
        if not inst:
            return

        def job():
            url, src, note = inst.web_auth_url()
            if not url:
                return False, note, url, src, ''
            state, detail = inst.auth_url_status(url)
            return True, note, url, src, detail

        def done(ok, result):
            url, src, detail = result[2], result[3], result[4]
            if ok and url:
                self._show_secret('入口地址（带 token）', url, src, detail)

        self._run_async('查看 Token · %s' % inst.label, job, on_done=done)

    # ---- 插件管理（第一阶段：我们自己的 GitHub 仓库）----
    def on_plugins(self, *_):
        inst = self._need()
        if not inst:
            return
        dlg = Gtk.Dialog(title='插件 · %s' % inst.label, transient_for=self, modal=True)
        dlg.add_buttons('关闭', Gtk.ResponseType.CLOSE)
        dlg.set_default_size(880, 580)
        area = dlg.get_content_area()
        area.set_border_width(14)
        area.set_spacing(10)

        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup('<b>插件 · %s</b>\n'
                        '从我们自己的 GitHub 仓库安装 / 卸载；装在这个实例自己的 profile 里：\n'
                        '<tt>%s</tt>' % (GLib.markup_escape_text(inst.label),
                                         GLib.markup_escape_text(plug.profile_dir(inst))))
        area.pack_start(head, False, False, 0)

        store = Gtk.ListStore(str, str, str, str)      # id, 说明, 状态, 版本
        tree = Gtk.TreeView(model=store)
        for idx, (title, width) in enumerate((('插件', 210), ('仓库 / 说明', 420),
                                              ('状态', 100), ('版本', 80))):
            renderer = Gtk.CellRendererText()
            renderer.set_property('ellipsize', 3)
            col = Gtk.TreeViewColumn(title, renderer)
            col.add_attribute(renderer, 'text', idx)
            col.set_min_width(width)
            col.set_resizable(True)
            tree.append_column(col)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.get_style_context().add_class('panel')
        sw.add(tree)
        area.pack_start(sw, True, True, 0)

        note = Gtk.Label(xalign=0, wrap=True)
        note.get_style_context().add_class('dim-label')
        area.pack_start(note, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_install = Gtk.Button(label='安装 / 更新')
        btn_install.get_style_context().add_class('primary')
        btn_uninstall = Gtk.Button(label='卸载')
        btn_uninstall.get_style_context().add_class('danger')
        btn_refresh = Gtk.Button(label='刷新状态')
        btn_repo = Gtk.Button(label='打开仓库')
        btn_import = Gtk.Button(label='导入本地包…')
        for btn in (btn_install, btn_uninstall, btn_import, btn_refresh, btn_repo):
            row.pack_start(btn, False, False, 0)
        area.pack_start(row, False, False, 0)

        state = {'busy': False}

        def current():
            model, it = tree.get_selection().get_selected()
            return model[it][0] if it is not None else None

        def fill(select=None):
            store.clear()
            status = plug.installed(inst)
            for item in plug.all_entries(inst):
                st = status.get(item['id'], {})
                if st.get('installed'):
                    label = '已安装'
                elif st.get('package_on_disk') or st.get('registered'):
                    label = '半装（需修）'
                elif item.get('local_only'):
                    label = '未发布'
                else:
                    label = '未安装'
                src = item['repo'] or '（未发布到 GitHub，可本地导入）'
                if item.get('extra'):
                    src = '（实例里已装，不在目录中）'
                it = store.append([item['id'], '%s · %s' % (src, item['desc']),
                                   label, st.get('version') or '-'])
                if select and item['id'] == select:
                    tree.get_selection().select_iter(it)
            if tree.get_selection().get_selected()[1] is None and store.iter_n_children(None):
                tree.get_selection().select_iter(store.get_iter_first())
            btn_install.set_sensitive(not state['busy'])
            btn_uninstall.set_sensitive(not state['busy'])

        def do(action):
            pid = current()
            if not pid:
                return
            entry = plug.find(pid)
            state['busy'] = True
            fill(select=pid)
            note.set_text('正在%s %s…（首次会从 GitHub 下载 tarball）' % (action, pid))

            def work():
                def log(line):
                    self.append_log('[plugin] %s' % line)
                if action == '安装':
                    ok, msg = plug.install(inst, entry, log=log)
                else:
                    ok, msg = plug.uninstall(inst, entry=entry, pid=pid, log=log)

                def done():
                    state['busy'] = False
                    self.append_log(('✔ ' if ok else '✘ ') + msg)
                    fill(select=pid)
                    note.set_text(msg + ('　（重启该实例的服务后生效）' if ok else ''))
                    return False
                GLib.idle_add(done)

            threading.Thread(target=work, daemon=True).start()

        def open_repo(*_):
            pid = current()
            if not pid:
                return
            url = 'https://github.com/%s' % plug.find(pid)['repo']
            try:
                subprocess.Popen(['xdg-open', url])
            except Exception as exc:
                self.append_log('✘ 打开仓库失败：%s' % exc)

        def import_tarball(*_):
            chooser = Gtk.FileChooserDialog(title='选择插件包（.tar.gz）', transient_for=dlg,
                                            action=Gtk.FileChooserAction.OPEN)
            chooser.add_buttons('取消', Gtk.ResponseType.CANCEL, '导入', Gtk.ResponseType.OK)
            flt = Gtk.FileFilter()
            flt.set_name('插件包 (*.tar.gz, *.tgz)')
            for pat in ('*.tar.gz', '*.tgz'):
                flt.add_pattern(pat)
            chooser.add_filter(flt)
            path = ''
            if chooser.run() == Gtk.ResponseType.OK:
                path = chooser.get_filename() or ''
            chooser.destroy()
            if not path:
                return
            state['busy'] = True
            fill()
            note.set_text('正在导入 %s…' % os.path.basename(path))

            def work():
                def log(line):
                    self.append_log('[plugin] %s' % line)
                ok, msg = plug.install_from_tarball(inst, path, log=log)

                def done():
                    state['busy'] = False
                    self.append_log(('✔ ' if ok else '✘ ') + msg)
                    fill()
                    note.set_text(msg + ('　（重启该实例的服务后生效）' if ok else ''))
                    return False
                GLib.idle_add(done)

            threading.Thread(target=work, daemon=True).start()

        btn_import.connect('clicked', import_tarball)
        btn_install.connect('clicked', lambda *a: do('安装'))
        btn_uninstall.connect('clicked', lambda *a: do('卸载'))
        btn_refresh.connect('clicked', lambda *a: fill(select=current()))
        btn_repo.connect('clicked', open_repo)

        fill()
        note.set_text('安装后需要重启该实例的服务才会加载：先「停止服务」再「启动服务」。')
        dlg.show_all()
        dlg.run()
        dlg.destroy()
    # ---- 更新 ----
    def on_update(self, *_):
        inst = self._need()
        if not inst:
            return
        dlg = Gtk.Dialog(title='更新 %s' % inst.label, transient_for=self, modal=True)
        dlg.add_buttons('取消', Gtk.ResponseType.CANCEL, '更新', Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=8, row_spacing=10, border_width=12)
        dlg.get_content_area().add(grid)

        # 与「新建」一致：立刻显示、后台拉版本、点开可滚动，并能选 latest
        picker_dsh = VersionPicker(['latest', inst.dsh_version or DEFAULT_DSH],
                                   value=inst.dsh_version or DEFAULT_DSH)
        picker_node = VersionPicker(['latest', inst.node_version or DEFAULT_NODE],
                                    value=inst.node_version or DEFAULT_NODE)

        ver_state = {'done': False}
        ver_bar = make_pulse_bar()
        ver_lbl = Gtk.Label(xalign=0, wrap=True)
        ver_lbl.set_text('正在联网获取可用版本…')
        ver_lbl.get_style_context().add_class('dim-label')
        box_ver = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box_ver.pack_start(ver_lbl, False, False, 0)
        box_ver.pack_start(ver_bar, False, False, 0)
        pulse_until(ver_bar, ver_state)
        dlg.connect('destroy', lambda *a: ver_state.__setitem__('done', True))

        def fetch_versions():
            try:
                dsh_list = self.manager.available_dsh_versions(14)
                node_list = self.manager.available_node_versions()
            except Exception:
                dsh_list, node_list = [], []

            def apply():
                ver_state['done'] = True
                try:
                    ver_bar.hide()
                    ver_lbl.set_text('版本列表已就绪（latest = 最新的非 alpha 版本）')
                    picker_dsh.set_options(['latest'] + [v for v in dsh_list if v != 'latest'])
                    picker_node.set_options(['latest'] + [v for v in node_list if v != 'latest'])
                except Exception:
                    pass
                return False
            GLib.idle_add(apply)

        threading.Thread(target=fetch_versions, daemon=True).start()

        grid.attach(Gtk.Label(label='dsh 版本', xalign=0), 0, 0, 1, 1)
        grid.attach(picker_dsh, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label='Node 版本', xalign=0), 0, 1, 1, 1)
        grid.attach(picker_node, 1, 1, 1, 1)
        grid.attach(box_ver, 0, 2, 2, 1)
        note = Gtk.Label(xalign=0, wrap=True)
        note.set_text('更新只动这个实例的目录；正在跑的话先停服务再更新（服务会自动另起）。')
        note.get_style_context().add_class('dim-label')
        grid.attach(note, 0, 3, 2, 1)
        dlg.show_all()
        if dlg.run() != Gtk.ResponseType.OK:
            ver_state['done'] = True
            dlg.destroy()
            return
        dsh = picker_dsh.get_value() or inst.dsh_version or DEFAULT_DSH
        node = picker_node.get_value() or inst.node_version or DEFAULT_NODE
        ver_state['done'] = True
        dlg.destroy()
        self._run_async('更新 %s → dsh %s' % (inst.label, dsh),
                        lambda: self.manager.update(inst.prefix, dsh, node))

    # ---- 修复 ----
    def on_repair(self, *_):
        inst = self._need()
        if not inst:
            return
        self._run_async('修复 %s' % inst.label, lambda: self.manager.repair(inst.prefix))

    # ---- 卸载 ----
    def on_uninstall(self, *_):
        inst = self._need()
        if not inst:
            return
        if not self._confirm('卸载「%s」？' % inst.label,
                             '会删除整个目录（含 Node、dsh 与该实例的数据目录）：\n%s' % inst.prefix):
            return
        self._run_async('卸载 %s' % inst.label, lambda: (self.manager.uninstall(inst.prefix),)[::2])


def _write_crash_log(tb, tag='gui'):
    try:
        os.makedirs(config_dir(), exist_ok=True)
        with open(os.path.join(config_dir(), 'crash.log'), 'a', encoding='utf-8') as fh:
            fh.write('\n===== %s %s =====\n%s' % (MANAGER_VERSION, tag, tb))
    except Exception:
        pass


def run_gui():
    """构造窗口并进入主循环。

    带主题构造失败时，自动退回「默认皮肤」再试一次——主题是纯外观，
    绝不能因为它让整个管理器起不来。两次都失败才抛给调用方（那里会弹错误窗）。
    """
    try:
        win = ManagerWindow()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        _write_crash_log(tb, 'with-theme')
        os.environ['DSH_MANAGER_NO_THEME'] = '1'
        try:
            win = ManagerWindow()
        except Exception:
            raise
        sys.stderr.write('[dsh-manager] 带主题启动失败，已自动改用 GTK 默认皮肤：\n' + tb)
    win.connect('destroy', Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


def show_crash_dialog(traceback_text):
    """启动失败时弹一个最朴素的错误窗：能看、能复制。

    这里刻意只用最少的 GTK 功能（窗口 + 标签 + 文本框 + 按钮），不加载主题，
    免得"报错窗自己也因为同一个原因崩掉"。
    """
    win = Gtk.Window(title='管理器启动失败')
    win.set_default_size(860, 580)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_border_width(14)

    head = Gtk.Label(xalign=0, wrap=True)
    head.set_markup('<b>管理器没能启动</b>\n'
                    '下面是完整堆栈，复制给我就能定位；同时写入了 '
                    '<tt>~/.config/dsh-manager/crash.log</tt>')
    box.pack_start(head, False, False, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    view = Gtk.TextView()
    view.set_editable(False)
    view.set_monospace(True)
    view.get_buffer().set_text(traceback_text)
    sw.add(view)
    box.pack_start(sw, True, True, 0)

    row = Gtk.Box(spacing=8)
    btn_copy = Gtk.Button(label='复制堆栈')

    def do_copy(*_):
        try:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(traceback_text, -1)
        except Exception:
            pass

    btn_copy.connect('clicked', do_copy)
    btn_close = Gtk.Button(label='关闭')
    btn_close.connect('clicked', lambda *a: win.destroy())
    row.pack_end(btn_close, False, False, 0)
    row.pack_end(btn_copy, False, False, 0)
    box.pack_start(row, False, False, 0)

    win.add(box)
    win.connect('destroy', Gtk.main_quit)
    win.show_all()
    Gtk.main()
