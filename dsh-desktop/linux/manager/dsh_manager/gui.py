# -*- coding: utf-8 -*-
"""dsh-manager 图形界面（GTK3）。

一次装好、长期用：在同一个窗口里管多个 DSH 实例 ——
每个实例有自己的安装目录、Node、dsh 版本、数据目录和端口，互不干扰。
"""
import json
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
def _gtk_version():
    """GTK 版本字符串；桩 GTK / 老版本取不到时退化成 0.0.0，绝不让它抛错。"""
    parts = []
    for fn in ('get_major_version', 'get_minor_version', 'get_micro_version'):
        try:
            parts.append(int(getattr(Gtk, fn)()))
        except Exception:
            parts.append(0)
    return '%d.%d.%d' % tuple(parts)


gtk_ver = _gtk_version()

THEME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'theme')
_PROVIDER = {'provider': None}


def theme_index():
    """主题索引（由 tools/build-gtk-theme.py 生成）：7 套 × 日/夜。"""
    try:
        with open(os.path.join(THEME_DIR, 'index.json'), encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {'order': ['frost'], 'variants': ['frost-day', 'frost-night'],
                'labels': {'frost-day': ['毛玻璃', '日间'],
                           'frost-night': ['毛玻璃', '夜间']}}


def last_theme_error():
    """上一次主题加载失败的原因（供界面显示；成功时为空）。"""
    return _PROVIDER.get('error') or ''


def theme_path(theme, mode):
    return os.path.join(THEME_DIR, '%s-%s.css' % (theme, mode))


def load_css(theme='frost', mode='day'):
    """挂上设计稿主题（Kimi 那套：7 主题 × 日/夜）。

    主题文件由 tools/build-gtk-theme.py 从 design/styles.css 的令牌生成，
    所以色值与设计稿逐项一致（tools/theme-token-check.py 会核对）。
    关掉主题：DSH_MANAGER_NO_THEME=1，或 settings.theme 置空。
    返回 (是否加载, 实际主题, 实际模式)。
    """
    if os.environ.get('DSH_MANAGER_NO_THEME') == '1':
        return False, theme, mode
    path = theme_path(theme, mode)
    if not os.path.exists(path):
        theme, mode = 'frost', 'day'
        path = theme_path(theme, mode)
    try:
        provider = Gtk.CssProvider()
        provider.load_from_path(path)
    except Exception as exc:                     # 文件缺失 / GTK 语法不被支持
        _PROVIDER['error'] = str(exc)
        sys.stderr.write('[dsh-manager] 主题未加载（继续用默认皮肤）：%s\n' % exc)
        return False, theme, mode
    _PROVIDER['error'] = ''
    screen = Gdk.Screen.get_default()
    if screen is None:
        return False, theme, mode
    old = _PROVIDER.get('provider')
    if old is not None:                          # 换主题时先摘掉旧的，避免叠加
        try:
            Gtk.StyleContext.remove_provider_for_screen(screen, old)
        except Exception:
            pass
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    _PROVIDER['provider'] = provider
    return True, theme, mode


class VersionPicker(Gtk.Box):
    """版本选择器 = 原生下拉框（ComboBoxText）+ 手动输入 + 「更新」按钮。

    以前用的是 Gtk.MenuButton + 自定义 Popover + ListBox（为了长列表能滚）。
    实测在用户的 Wayland/KDE 桌面上**点了没反应**：那套 popover 依赖自定义样式和
    行激活事件，出问题时不好定位。现在退回最稳的 `Gtk.ComboBoxText`（原生下拉、
    键盘鼠标都能选），列表先用**预设版本号**填满，右边一个「更新」按钮联网刷新，
    新列表**覆盖**旧的；旁边保留手动输入框，任何情况下都能直接打版本号。
    """

    def __init__(self, options=None, value=None, width_chars=16, fetcher=None, hint=None):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._value = ''
        self._fetcher = fetcher
        self.set_valign(Gtk.Align.CENTER)

        self._combo = Gtk.ComboBoxText()
        self._combo.set_size_request(width_chars * 9, -1)
        self._combo.set_valign(Gtk.Align.CENTER)
        self._combo.set_tooltip_text('点开选择版本号')
        self._combo.connect('changed', self._on_combo_changed)
        self.pack_start(self._combo, False, False, 0)

        self._entry = Gtk.Entry()
        self._entry.set_width_chars(18)
        self._entry.set_placeholder_text(hint or '或手动输入版本号')
        self._entry.set_tooltip_text('手动输入的版本优先于下拉框')
        self.pack_start(self._entry, True, True, 0)

        self._btn = None
        if fetcher is not None:
            self._btn = Gtk.Button(label='更新')
            self._btn.set_tooltip_text('联网重新获取版本列表，并用新列表覆盖当前列表')
            self._btn.set_valign(Gtk.Align.CENTER)
            self._btn.connect('clicked', self._on_refresh)
            self.pack_start(self._btn, False, False, 0)

        self.set_options(options or [])
        if value:
            self.set_value(value)

    # ---- 列表 ----
    def set_options(self, options):
        options = [o for o in (options or []) if o]
        current = self._value or self._combo.get_active_text() or ''
        self._combo.remove_all()
        for opt in options:
            self._combo.append_text(opt)
        if not options:
            self._value = ''
            return
        if current in options:
            self._combo.set_active(options.index(current))
        else:
            self._combo.set_active(0)
            self._value = options[0]

    def _on_combo_changed(self, combo):
        text = combo.get_active_text()
        if text:
            self._value = text

    def set_value(self, value):
        value = value or ''
        self._value = value
        if value == '':
            self._combo.set_active(-1)
            return
        model = self._combo.get_model()
        if model is not None:
            for row in model:
                if row[0] == value:
                    self._combo.set_active_iter(row.iter)
                    return
        # 不在列表里：加进去并选中（手动输入的版本也能显示出来）
        self._combo.append_text(value)
        self._combo.set_active(self._combo.get_model().iter_n_children(None) - 1)

    def get_value(self):
        """手动输入优先；否则用下拉框当前项。"""
        manual = self._entry.get_text().strip()
        if manual:
            return manual
        return self._combo.get_active_text() or self._value or ''

    # ---- 联网刷新（覆盖旧列表）----
    def _on_refresh(self, *_a):
        if self._btn is not None:
            self._btn.set_sensitive(False)
            self._btn.set_label('更新中…')

        def work():
            items, err = [], ''
            try:
                items = list(self._fetcher() or [])
            except Exception as exc:
                err = '%s: %s' % (type(exc).__name__, exc)
            GLib.idle_add(self._apply_refresh, items, err)

        threading.Thread(target=work, daemon=True).start()

    def _apply_refresh(self, items, err):
        try:
            if items:
                self.set_options(['latest'] + [v for v in items if v != 'latest'])
            if self._btn is not None:
                self._btn.set_sensitive(True)
                if items:
                    self._btn.set_label('更新')
                    self._btn.set_tooltip_text('已更新：%d 个版本' % len(items))
                else:
                    self._btn.set_label('更新')
                    self._btn.set_tooltip_text('更新失败：%s' % (err or '拿不到列表'))
        except Exception:
            pass
        return False


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
        # 主题只是外观：想回到 GTK 默认皮肤，设 DSH_MANAGER_NO_THEME=1 或在设置里清空主题。
        theme, mode = self._theme_state()
        self.theme_loaded, theme, mode = load_css(theme, mode)
        self._fit_to_screen()
        self._build()
        self._sync_theme_labels(theme, mode)
        self.refresh()
        if not self.theme_loaded and os.environ.get('DSH_MANAGER_NO_THEME') != '1':
            self.append_log('✘ 主题未加载：%s（界面会用 GTK 默认皮肤）' % (last_theme_error() or '未知原因'))
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
            # 设计稿画布是 1440x900：能放下就用它，放不下按屏幕收缩（留 60px 余量）
            width = max(900, min(1440, area.width - 60))
            height = max(560, min(900, area.height - 60))
            self.win_width = width
            self.win_height = height
            self.set_default_size(width, height)
            self.resize(width, height)
        except Exception:
            pass

    # ------------------------------------------------------------ 主题
    def _theme_state(self):
        """当前主题/模式（兼容老版本 settings 里的布尔值）。"""
        theme = self.settings.get('theme')
        if isinstance(theme, bool):
            theme = 'frost' if theme else ''
        theme = (theme or '').strip() or 'frost'
        index = theme_index()
        if theme not in index.get('order', []):
            theme = (index.get('order') or ['frost'])[0]
        mode = self.settings.get('mode') or 'day'
        if mode not in ('day', 'night'):
            mode = 'day'
        return theme, mode

    def apply_theme(self, theme=None, mode=None, persist=True):
        """切主题 / 日夜：换 CSS、更新顶栏标签、可选落盘。"""
        cur_theme, cur_mode = self._theme_state()
        theme = theme or cur_theme
        mode = mode or cur_mode
        ok, theme, mode = load_css(theme, mode)
        self.theme_loaded = ok
        self.settings['theme'] = theme if ok else ''
        self.settings['mode'] = mode
        if persist and ok:
            save_settings({'theme': theme, 'mode': mode})
        self._sync_theme_labels(theme, mode)
        return ok

    def _sync_theme_labels(self, theme, mode):
        """把当前主题/模式写到界面各处（顶栏、设置页、菜单勾选）。"""
        index = theme_index()
        labels = index.get('labels', {}).get('%s-%s' % (theme, mode), [theme, mode])
        if getattr(self, 'lbl_theme_name', None) is not None:
            self.lbl_theme_name.set_text(labels[0])
        if getattr(self, 'btn_mode', None) is not None:
            self.btn_mode.set_label('☾  夜间' if mode == 'night' else '☀  日间')
        if getattr(self, 'lbl_settings_theme', None) is not None:
            self.lbl_settings_theme.set_text(labels[0])
            self.lbl_settings_mode.set_text(labels[1])
        self._mark_theme_menu(theme, mode)

    def _mark_theme_menu(self, theme, mode='day'):
        index = theme_index()
        for key, btn in getattr(self, '_theme_buttons', {}).items():
            ctx = btn.get_style_context()
            if key == theme:
                ctx.add_class('selected')
            else:
                ctx.remove_class('selected')
            labels = index.get('labels', {}).get('%s-%s' % (key, mode), [key, ''])
            btn.set_tooltip_text('%s · %s' % (labels[0], labels[1]))

    def on_toggle_mode(self, *_):
        _theme, mode = self._theme_state()
        self.apply_theme(mode=('day' if mode == 'night' else 'night'))
        self._toast('已切换到%s模式' % ('日间' if mode == 'night' else '夜间'))

    def on_pick_theme(self, widget):
        theme = getattr(widget, 'theme_key', '')
        if not theme:
            return
        self.apply_theme(theme=theme)
        pop = getattr(self, '_theme_popover', None)
        if pop is not None:
            pop.popdown()
        self._toast('主题已切换到「%s」' % (widget.get_label() if hasattr(widget, 'get_label') else theme))

    # ------------------------------------------------------------ 小工具
    @staticmethod
    def _label(text, *classes, **kwargs):
        lbl = Gtk.Label(label=text, xalign=kwargs.get('xalign', 0.0))
        if kwargs.get('wrap'):
            lbl.set_line_wrap(True)
        if kwargs.get('selectable'):
            lbl.set_selectable(True)
        for cls in classes:
            lbl.get_style_context().add_class(cls)
        return lbl

    @staticmethod
    def _icon(text, *classes):
        lbl = Gtk.Label(label=text, xalign=0.5, yalign=0.5)
        lbl.get_style_context().add_class('glyph')
        for cls in classes:
            lbl.get_style_context().add_class(cls)
        return lbl

    def _button(self, key, label, *classes, **kwargs):
        """建按钮并登记到 self.buttons（set_buttons_sensitive 用）。"""
        btn = Gtk.Button()
        if kwargs.get('icon'):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
            box.pack_start(self._icon(kwargs['icon']), False, False, 0)
            box.pack_start(Gtk.Label(label=label), False, False, 0)
            btn.add(box)
        else:
            btn.set_label(label)
        for cls in classes:
            btn.get_style_context().add_class(cls)
        handler = kwargs.get('handler')
        if handler is None:
            handler = getattr(self, 'on_' + key) if hasattr(self, 'on_' + key) else None
        if handler is not None:
            btn.connect('clicked', handler)
        if key:
            self.buttons[key] = btn
        return btn

    def _toast(self, text):
        """底部居中气泡（设计稿 .toast），2.6 秒后自动收起。"""
        try:
            self.lbl_toast.set_text(text)
            self.toast_revealer.set_reveal_child(True)
        except Exception:
            return

        def hide():
            try:
                self.toast_revealer.set_reveal_child(False)
            except Exception:
                pass
            return False
        GLib.timeout_add(2600, hide)

    # ------------------------------------------------------------ 界面
    def _build(self):
        self.buttons = {}
        self._need_selection = {'start', 'stop', 'open', 'reload', 'rebuild', 'token',
                                'folder', 'uninstall', 'plugins', 'update', 'repair'}
        self._theme_buttons = {}
        self._recent = []
        # 完整日志只存缓冲区（界面上的「最近日志」只显示 3 行；完整内容走对话框）
        self.log_buf = Gtk.TextBuffer()
        self.set_titlebar(None)          # 设计稿没有系统标题栏样式，用自绘顶栏
        self.get_style_context().add_class('dsh-window')

        toast = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toast.get_style_context().add_class('toast')
        toast.pack_start(self._icon('✓', 'toast-icon'), False, False, 0)
        self.lbl_toast = self._label('操作已完成', 'toast-text')
        toast.pack_start(self.lbl_toast, False, False, 0)
        self.toast_revealer = Gtk.Revealer()
        self.toast_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.toast_revealer.set_halign(Gtk.Align.CENTER)
        self.toast_revealer.set_valign(Gtk.Align.END)
        self.toast_revealer.set_margin_bottom(26)
        self.toast_revealer.add(toast)
        self.toast_revealer.set_reveal_child(False)

        overlay = Gtk.Overlay()
        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        shell.get_style_context().add_class('dsh-shell')
        shell.set_margin_top(20)
        shell.set_margin_bottom(20)
        shell.set_margin_start(20)
        shell.set_margin_end(20)
        overlay.add(shell)
        overlay.add_overlay(self.toast_revealer)
        self.add(overlay)

        shell.pack_start(self._build_sidebar(), False, False, 0)
        shell.pack_start(self._build_main(), True, True, 0)

        # 忙碌指示条（安装/更新期间）：放在顶栏下面，不打断布局
        self.busy_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.busy_box.get_style_context().add_class('busy-bar')
        self.busy_lbl = self._label('', 'busy-text')
        self.busy_bar = make_pulse_bar()
        self.busy_box.pack_start(self.busy_lbl, False, False, 0)
        self.busy_box.pack_start(self.busy_bar, True, True, 0)
        self.busy_box.set_no_show_all(True)
        self.main_box.pack_start(self.busy_box, False, False, 0)
        self.busy_box.hide()
        self._busy_pulse_id = None

        self.set_buttons_sensitive(False)

    # ---- 侧栏 ----
    def _build_sidebar(self):
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        side.get_style_context().add_class('sidebar')
        side.set_size_request(248, -1)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        brand.set_margin_bottom(24)
        mark = self._label('D', 'brand-mark')
        mark.set_size_request(38, 38)
        brand.pack_start(mark, False, False, 0)
        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        brand_text.pack_start(self._label('DeepSeek Harness', 'brand-title'), False, False, 0)
        brand_text.pack_start(self._label('管理器 v%s' % MANAGER_VERSION, 'brand-sub'),
                              False, False, 0)
        brand.pack_start(brand_text, False, False, 0)
        side.pack_start(brand, False, False, 0)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        head.get_style_context().add_class('side-section-title')
        head.pack_start(self._label('我的实例', 'side-section-title'), False, False, 0)
        self.lbl_count = self._label('0', 'count-pill')
        head.pack_start(self.lbl_count, False, False, 0)
        btn_add = self._button('new', '', 'icon-btn', 'small', icon='＋')
        btn_add.set_tooltip_text('新建实例')
        btn_add.set_margin_start(6)
        head.pack_end(btn_add, False, False, 0)
        side.pack_start(head, False, False, 0)

        self.instance_list = Gtk.ListBox()
        self.instance_list.get_style_context().add_class('instance-list')
        self.instance_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.instance_list.connect('row-selected', self.on_row_selected)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(self.instance_list)
        side.pack_start(sw, True, True, 0)

        btn_new = self._button('new', '＋  新建实例', 'new-instance')
        btn_new.set_margin_top(12)
        btn_new.set_margin_start(4)
        btn_new.set_margin_end(4)
        side.pack_start(btn_new, False, False, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        bottom.set_margin_top(18)
        bottom.pack_start(self._label('工作空间', 'side-caption'), False, False, 0)
        self.btn_overview = self._button('', '▦  实例概览', 'side-link', 'selected',
                                         handler=lambda *a: self._show_page('dashboard'))
        bottom.pack_start(self.btn_overview, False, False, 0)
        self.btn_settings = self._button('settings', '⚙  管理器设置', 'side-link')
        bottom.pack_start(self.btn_settings, False, False, 0)
        self.btn_help = self._button('', '？  使用帮助', 'side-link',
                                     handler=self.on_help)
        bottom.pack_start(self.btn_help, False, False, 0)

        runtime = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        runtime.get_style_context().add_class('runtime')
        icon = self._label('Py', 'runtime-icon')
        icon.set_size_request(28, 28)
        runtime.pack_start(icon, False, False, 0)
        rt_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        rt_text.pack_start(self._label('运行环境正常', 'runtime-title'), False, False, 0)
        self.lbl_runtime = self._label(
            'Python %s · GTK %s' % (sys.version.split()[0], gtk_ver), 'runtime-sub')
        rt_text.pack_start(self.lbl_runtime, False, False, 0)
        runtime.pack_start(rt_text, True, True, 0)
        dot = self._label('', 'status-dot')
        dot.set_size_request(7, 7)
        runtime.pack_start(dot, False, False, 0)
        bottom.pack_start(runtime, False, False, 0)
        side.pack_start(bottom, False, False, 0)
        return side

    # ---- 主区 ----
    def _build_main(self):
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_box.pack_start(self._build_topbar(), False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)
        self.stack.add_named(self._build_dashboard(), 'dashboard')
        self.stack.add_named(self._build_settings_page(), 'settings')
        self.main_box.pack_start(self.stack, True, True, 0)
        return self.main_box

    def _build_topbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bar.get_style_context().add_class('topbar')

        crumb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        crumb.pack_start(self._label('工作空间', 'breadcrumb'), False, False, 0)
        crumb.pack_start(self._label('/', 'breadcrumb'), False, False, 0)
        self.lbl_crumb = self._label('实例概览', 'breadcrumb-current')
        crumb.pack_start(self.lbl_crumb, False, False, 0)
        bar.pack_start(crumb, False, False, 0)

        # 主题选择：MenuButton + Popover（设计稿 .theme-trigger / .theme-menu）
        trigger = Gtk.MenuButton()
        trigger.get_style_context().add_class('theme-trigger')
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        swatch = Gtk.Box()
        swatch.get_style_context().add_class('theme-swatch')
        swatch.set_size_request(14, 14)
        inner.pack_start(swatch, False, False, 0)
        self.lbl_theme_name = self._label('毛玻璃')
        inner.pack_start(self.lbl_theme_name, False, False, 0)
        inner.pack_start(self._icon('⌄'), False, False, 0)
        trigger.add(inner)

        popover = Gtk.Popover()
        popover.get_style_context().add_class('theme-menu')
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        menu.set_border_width(7)
        menu.pack_start(self._label('选择界面主题', 'menu-header'), False, False, 0)
        index = theme_index()
        for key in index.get('order', []):
            labels = index.get('labels', {}).get('%s-day' % key, [key, ''])
            row = Gtk.Button()
            row.get_style_context().add_class('flat')
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
            box.pack_start(self._label('●', 'theme-dot'), False, False, 0)
            name = Gtk.Label(label=labels[0], xalign=0.0)
            name.set_width_chars(10)
            box.pack_start(name, False, False, 0)
            hint = self._label(labels[1], 'theme-hint')
            box.pack_end(hint, False, False, 0)
            row.add(box)
            row.theme_key = key
            row.connect('clicked', self.on_pick_theme)
            menu.pack_start(row, False, False, 0)
            self._theme_buttons[key] = row
        popover.add(menu)
        trigger.set_popover(popover)
        self._theme_popover = popover
        self.btn_mode = self._button('', '☀  日间', 'mode-toggle',
                                     handler=self.on_toggle_mode)
        bar.pack_end(self.btn_mode, False, False, 0)
        info = self._button('', 'ⓘ', 'icon-btn', handler=self.on_about)
        info.set_tooltip_text('关于 / 版本信息')
        bar.pack_end(info, False, False, 0)
        bar.pack_end(trigger, False, False, 0)
        return bar

    def _build_dashboard(self):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.get_style_context().add_class('content')
        page.set_margin_top(22)
        page.set_margin_bottom(14)
        page.set_margin_start(26)
        page.set_margin_end(26)
        sw.add(page)

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        heading.set_margin_bottom(20)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        text.pack_start(self._label('INSTANCE OVERVIEW', 'eyebrow'), False, False, 0)
        title_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.lbl_title = self._label('选择左侧的实例', 'page-title')
        title_line.pack_start(self.lbl_title, False, False, 0)
        self.lbl_badge = self._label('—', 'badge')
        title_line.pack_start(self.lbl_badge, False, False, 0)
        text.pack_start(title_line, False, False, 0)
        text.pack_start(self._label('管理服务、窗口与扩展，让实例始终保持最佳状态。',
                                    'page-desc'), False, False, 0)
        heading.pack_start(text, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_valign(Gtk.Align.CENTER)
        self.btn_open = self._button('open', '打开窗口', 'btn', 'btn-primary', icon='↗')
        actions.pack_start(self.btn_open, False, False, 0)
        more = Gtk.MenuButton()
        more.get_style_context().add_class('btn')
        more.get_style_context().add_class('btn-secondary')
        more.add(self._icon('⋯'))
        more.set_tooltip_text('更多操作')
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        menu.set_border_width(6)
        for key, label, glyph in (
                ('token', '查看 Token', '⚿'),
                ('rebuild', '重建窗口', '↻'),
                ('folder', '在文件管理器中显示', '▤'),
                (None, None, None),
                ('uninstall', '卸载实例', '✕')):
            if key is None:
                menu.pack_start(Gtk.Separator(), False, False, 2)
                continue
            btn = self._button(key, label, 'flat', icon=glyph)
            if key == 'uninstall':
                btn.get_style_context().add_class('danger-text')
            menu.pack_start(btn, False, False, 0)
        pop = Gtk.Popover()
        pop.add(menu)
        more.set_popover(pop)
        actions.pack_start(more, False, False, 0)
        heading.pack_start(actions, False, False, 0)
        page.pack_start(heading, False, False, 0)

        # 两张卡：实例信息 / 快捷控制
        grid = Gtk.Grid(column_spacing=16, row_spacing=16)
        grid.set_column_homogeneous(False)
        info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        info_card.get_style_context().add_class('card')
        info_card.set_hexpand(True)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top.pack_start(self._label('实例信息', 'card-label'), False, False, 0)
        top.pack_end(self._label('本地实例', 'subtle-tag'), False, False, 0)
        info_card.pack_start(top, False, False, 0)
        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=13)
        meta.set_margin_top(16)
        self.lbl_avatar = self._label('--', 'large-avatar')
        self.lbl_avatar.set_size_request(48, 48)
        meta.pack_start(self.lbl_avatar, False, False, 0)
        meta_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.lbl_meta_name = self._label('—', 'meta-name')
        meta_text.pack_start(self.lbl_meta_name, False, False, 0)
        self.lbl_meta_path = self._label('—', 'meta-path')
        self.lbl_meta_path.set_selectable(True)
        meta_text.pack_start(self.lbl_meta_path, False, False, 0)
        pills = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pills.set_margin_top(4)
        self.lbl_pill_dsh = self._label('dsh —', 'version-pill')
        self.lbl_pill_node = self._label('Node —', 'version-pill')
        pills.pack_start(self.lbl_pill_dsh, False, False, 0)
        pills.pack_start(self.lbl_pill_node, False, False, 0)
        meta_text.pack_start(pills, False, False, 0)
        meta.pack_start(meta_text, True, True, 0)
        info_card.pack_start(meta, False, False, 0)
        sep = Gtk.Separator()
        sep.set_margin_top(14)
        info_card.pack_start(sep, False, False, 0)
        metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        metrics.set_margin_top(12)
        self.lbl_metric_pid = self._metric(metrics, '进程 PID', '—', first=True)
        self.lbl_metric_port = self._metric(metrics, '服务端口', '—')
        self.lbl_metric_status = self._metric(metrics, '运行状态', '—', accent=True)
        info_card.pack_start(metrics, False, False, 0)

        control = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        control.get_style_context().add_class('card')
        control.set_size_request(320, -1)
        ctop = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ctop.pack_start(self._label('快捷控制', 'card-label'), False, False, 0)
        self.lbl_live = self._label('● 服务正常', 'live-indicator')
        ctop.pack_end(self.lbl_live, False, False, 0)
        control.pack_start(ctop, False, False, 0)
        control.pack_start(self._control_row('服务', '后台进程与连接',
                                             [('start', '启动', '▶', ('btn', 'btn-secondary', 'compact')),
                                              ('stop', '停止', '■', ('btn', 'btn-danger-soft', 'compact'))]),
                           False, False, 0)
        line = Gtk.Separator()
        line.set_margin_top(14)
        control.pack_start(line, False, False, 0)
        control.pack_start(self._control_row('窗口', '界面与页面状态',
                                             [('reload', '重载', '↺', ('btn', 'btn-secondary', 'compact')),
                                              ('rebuild', '重建', '↻', ('btn', 'btn-secondary', 'compact'))]),
                           False, False, 0)
        grid.attach(info_card, 0, 0, 1, 1)
        grid.attach(control, 1, 0, 1, 1)
        page.pack_start(grid, False, False, 0)

        # 常用功能
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        section.set_margin_top(20)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        head.pack_start(self._label('常用功能', 'section-title'), False, False, 0)
        head.pack_start(self._label('管理实例的扩展与文件', 'section-sub'), False, False, 0)
        section.pack_start(head, False, False, 0)
        quick = Gtk.Grid(column_spacing=11, row_spacing=11)
        quick.set_column_homogeneous(True)
        for idx, (key, title, sub, glyph) in enumerate((
                ('token', '查看 Token', '访问凭证与连接信息', '⚿'),
                ('plugins', '管理插件', '安装、启用与配置扩展', '⊞'),
                ('update', '检查更新', '获取最新的 dsh 与 Node', '↓'),
                ('folder', '数据目录', '浏览配置与本地数据', '▤'))):
            btn = self._quick_action(key, title, sub, glyph)
            quick.attach(btn, idx, 0, 1, 1)
        section.pack_start(quick, False, False, 0)
        page.pack_start(section, False, False, 0)

        # 最近日志
        log_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        log_card.get_style_context().add_class('card')
        log_card.set_margin_top(20)
        lhead = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lhead.get_style_context().add_class('log-header')
        lhead.pack_start(self._icon('▶'), False, False, 0)
        lhead.pack_start(self._label('最近日志', 'log-title'), False, False, 0)
        self.lbl_log_count = self._label('0', 'log-count')
        lhead.pack_start(self.lbl_log_count, False, False, 0)
        view_btn = self._button('', '查看完整日志  →', 'text-btn', handler=self.on_view_log)
        lhead.pack_end(view_btn, False, False, 0)
        log_card.pack_start(lhead, False, False, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        body.set_margin_top(8)
        self.log_rows = []
        for _ in range(3):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            t = self._label('', 'log-time')
            lvl = self._label('', 'log-level')
            msg = self._label('', 'log-line')
            msg.set_ellipsize(3)
            row.pack_start(t, False, False, 0)
            row.pack_start(lvl, False, False, 0)
            row.pack_start(msg, True, True, 0)
            body.pack_start(row, False, False, 0)
            self.log_rows.append((t, lvl, msg))
        log_card.pack_start(body, False, False, 0)
        page.pack_start(log_card, False, False, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_top(12)
        footer.pack_start(self._label('●  所有更改已自动保存', 'page-footer'), False, False, 0)
        self.lbl_footer_root = self._label('实例根目录 · %s' % self.manager.root, 'page-footer')
        footer.pack_end(self.lbl_footer_root, False, False, 0)
        page.pack_start(footer, False, False, 0)
        return sw

    def _metric(self, parent, label, value, first=False, accent=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.set_hexpand(True)
        if not first:
            box.set_margin_start(14)
            sep = None
        box.pack_start(self._label(label, 'metric-label'), False, False, 0)
        val = self._label(value, 'metric-value', *(['accent'] if accent else []))
        box.pack_start(val, False, False, 0)
        parent.pack_start(box, True, True, 0)
        return val

    def _control_row(self, title, sub, buttons):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_margin_top(18)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        text.pack_start(self._label(title, 'control-title'), False, False, 0)
        text.pack_start(self._label(sub, 'control-sub'), False, False, 0)
        row.pack_start(text, True, True, 0)
        holder = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for key, label, glyph, classes in buttons:
            btn = self._button(key, label, *classes, icon=glyph)
            holder.pack_start(btn, False, False, 0)
        row.pack_end(holder, False, False, 0)
        return row

    def _quick_action(self, key, title, sub, glyph):
        btn = Gtk.Button()
        btn.get_style_context().add_class('quick-action')
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        icon = self._icon(glyph, 'quick-icon')
        icon.set_size_request(34, 34)
        box.pack_start(icon, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text.pack_start(self._label(title, 'quick-title'), False, False, 0)
        sub_lbl = self._label(sub, 'quick-sub')
        sub_lbl.set_ellipsize(3)
        text.pack_start(sub_lbl, False, False, 0)
        box.pack_start(text, True, True, 0)
        box.pack_end(self._icon('→', 'quick-arrow'), False, False, 0)
        btn.add(box)
        self.buttons[key] = btn
        handler = getattr(self, 'on_' + key, None)
        if handler is not None:
            btn.connect('clicked', handler)
        return btn

    # ---- 设置页（设计稿的第二页） ----
    def _build_settings_page(self):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.get_style_context().add_class('content')
        page.set_margin_top(22)
        page.set_margin_bottom(14)
        page.set_margin_start(26)
        page.set_margin_end(26)
        sw.add(page)

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        heading.set_margin_bottom(18)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        text.pack_start(self._label('MANAGER PREFERENCES', 'eyebrow'), False, False, 0)
        text.pack_start(self._label('管理器设置', 'page-title'), False, False, 0)
        text.pack_start(self._label('查看运行环境，管理外观与维护选项。', 'page-desc'),
                        False, False, 0)
        heading.pack_start(text, True, True, 0)
        heading.pack_start(self._button('saveSettings', '✓  保存设置', 'btn', 'btn-primary',
                                        handler=self.on_save_settings), False, False, 0)
        page.pack_start(heading, False, False, 0)

        grid = Gtk.Grid(column_spacing=16, row_spacing=16)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        left.pack_start(self._info_card(), False, False, 0)
        left.pack_start(self._maintenance_card(), False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        right.pack_start(self._appearance_card(), False, False, 0)
        right.set_size_request(340, -1)
        grid.attach(left, 0, 0, 1, 1)
        grid.attach(right, 1, 0, 1, 1)
        page.pack_start(grid, False, False, 0)
        return sw

    def _settings_card(self, glyph, title, sub):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.get_style_context().add_class('card')
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        icon = self._icon(glyph, 'quick-icon')
        icon.set_size_request(34, 34)
        head.pack_start(icon, False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        titles.pack_start(self._label(title, 'card-label'), False, False, 0)
        titles.pack_start(self._label(sub, 'card-sub'), False, False, 0)
        head.pack_start(titles, True, True, 0)
        card.pack_start(head, False, False, 0)
        return card

    def _info_card(self):
        card = self._settings_card('ⓘ', '管理器信息', '当前安装与运行环境')
        lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        lines.set_margin_top(14)
        for key, value in (
                ('管理器版本', 'v%s' % MANAGER_VERSION),
                ('程序目录', MANAGER_LIB),
                ('配置目录', config_dir()),
                ('运行环境', 'Python %s · GTK %s' % (sys.version.split()[0], gtk_ver)),
                ('实例根目录', self.manager.root)):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            name = self._label(key, 'metric-label')
            name.set_width_chars(12)
            row.pack_start(name, False, False, 0)
            val = self._label(value, 'metric-value')
            val.set_selectable(True)
            val.set_ellipsize(3)
            row.pack_start(val, True, True, 0)
            lines.pack_start(row, False, False, 0)
        card.pack_start(lines, False, False, 0)
        return card

    def _maintenance_card(self):
        card = self._settings_card('⚒', '维护与诊断', '排查问题或重新安装管理器')
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(14)
        box.pack_start(self._button('', '查看管理器日志', 'btn', 'btn-secondary', icon='▶',
                                    handler=self.on_view_log), False, False, 0)
        box.pack_start(self._button('', '复制诊断信息', 'btn', 'btn-secondary', icon='▣',
                                    handler=self.on_copy_diag), False, False, 0)
        box.pack_start(self._button('repair', '修复 / 重装', 'btn', 'btn-secondary', icon='⚒'),
                       False, False, 0)
        card.pack_start(box, False, False, 0)
        return card

    def _appearance_card(self):
        card = self._settings_card('◑', '外观与日志', '个性化你的工作空间')
        card.pack_start(self._label('界面主题', 'field-label'), False, False, 0)
        preview = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        preview.set_margin_top(6)
        swatch = Gtk.Box()
        swatch.get_style_context().add_class('theme-swatch')
        swatch.set_size_request(16, 16)
        preview.pack_start(swatch, False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.lbl_settings_theme = self._label('毛玻璃', 'quick-title')
        self.lbl_settings_mode = self._label('日间', 'quick-sub')
        names.pack_start(self.lbl_settings_theme, False, False, 0)
        names.pack_start(self.lbl_settings_mode, False, False, 0)
        preview.pack_start(names, True, True, 0)
        preview.pack_end(self._button('', '更换主题', 'text-btn', handler=self.on_cycle_theme),
                         False, False, 0)
        card.pack_start(preview, False, False, 0)

        hint = self._label('日志面板保留行数', 'field-label')
        hint.set_margin_top(14)
        card.pack_start(hint, False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(6)
        spin = Gtk.SpinButton.new_with_range(100, 5000, 50)
        spin.set_value(int(self.settings.get('logLines') or 800))
        spin.set_hexpand(True)
        row.pack_start(spin, True, True, 0)
        row.pack_start(self._label('行', 'field-hint'), False, False, 0)
        card.pack_start(row, False, False, 0)
        self.spin_log_lines = spin
        note = self._label('主题切换会立即生效，无需重启管理器。', 'field-hint')
        note.set_margin_top(10)
        card.pack_start(note, False, False, 0)
        if not getattr(self, 'theme_loaded', True):
            warn = self._label('主题未加载：%s' % (last_theme_error() or '未知原因')[:160],
                               'field-hint', wrap=True)
            warn.set_margin_top(6)
            card.pack_start(warn, False, False, 0)
        return card

    # ---- 页面切换 ----
    def _show_page(self, name):
        self.stack.set_visible_child_name(name)
        for btn, key in ((self.btn_overview, 'dashboard'), (self.btn_settings, 'settings')):
            ctx = btn.get_style_context()
            if key == name:
                ctx.add_class('selected')
            else:
                ctx.remove_class('selected')
        self.lbl_crumb.set_text('实例概览' if name == 'dashboard' else '管理器设置')

    def on_help(self, *_):
        self._text_dialog('使用帮助',
                          '\n'.join([
                              'DeepSeek Harness 管理器 v%s' % MANAGER_VERSION,
                              '',
                              '· 左侧列表选择实例，右侧卡片显示状态；「打开窗口」唤起桌面窗口。',
                              '· 「窗口」组：重载页面（页面脚本卡住时用）、重建窗口（画面坏掉时用）。',
                              '· 「查看 Token」把带 token 的入口地址显示在日志里，并复制到剪贴板。',
                              '· 「管理插件…」从我们自己的 GitHub 仓库给该实例安装/卸载插件。',
                              '· 顶栏右侧：切换 7 套主题与日/夜模式（立即生效）。',
                              '',
                              '排障：设置页 →「复制诊断信息」，或 <前缀>/logs/desktop.log。',
                          ]))

    def on_about(self, *_):
        self._text_dialog('关于', '\n'.join([
            'DeepSeek Harness 管理器 v%s' % MANAGER_VERSION,
            '界面：7 套主题 × 日/夜（token 从 design/styles.css 抽取生成）',
            '程序目录：%s' % MANAGER_LIB,
            '配置目录：%s' % config_dir(),
            '运行环境：Python %s · GTK %s' % (sys.version.split()[0], gtk_ver),
        ]))

    def on_copy_diag(self, *_):
        text = self._diagnostics_text()
        self._copy(text)
        self._toast('诊断信息已复制到剪贴板')

    def on_cycle_theme(self, *_):
        index = theme_index()
        order = index.get('order') or ['frost']
        theme, _mode = self._theme_state()
        nxt = order[(order.index(theme) + 1) % len(order)] if theme in order else order[0]
        self.apply_theme(theme=nxt)
        self._toast('主题已切换到「%s」' % index.get('labels', {}).get('%s-day' % nxt, [nxt])[0])

    def on_save_settings(self, *_):
        values = {'theme': self.settings.get('theme') or '',
                  'mode': self.settings.get('mode') or 'day',
                  'logLines': int(self.spin_log_lines.get_value())}
        ok = save_settings(values)
        self.settings.update(values)
        self._toast('设置已保存' if ok else '保存失败（配置目录不可写？）')

    def on_view_log(self, *_):
        lines = read_manager_log(400)
        buffer = self.log_buf.get_text(self.log_buf.get_start_iter(),
                                       self.log_buf.get_end_iter(), False)
        live = [line for line in buffer.splitlines() if line.strip()]
        head = ['—— 管理器日志 ——',
                '文件：%s' % manager_log_path(),
                '文件里 %d 行；下面是本次运行的面板日志（%d 行）+ 文件最后 400 行' % (len(lines), len(live)),
                '']
        body = (['【本次运行】'] + live if live else []) + (['', '【已落盘】'] + lines if lines else [])
        self._text_dialog('管理器日志', '\n'.join(head + (body or ['（还没有日志）'])))

    def _diagnostics_text(self):
        parts = ['DeepSeek Harness 管理器 v%s' % MANAGER_VERSION,
                 '主题: %s / %s' % self._theme_state(),
                 '程序目录: %s' % MANAGER_LIB,
                 '配置目录: %s' % config_dir(),
                 '运行环境: Python %s · GTK %s' % (sys.version.split()[0], gtk_ver),
                 '实例根目录: %s' % self.manager.root,
                 '', '实例:']
        for inst in self.manager.list_instances():
            parts.append('  - %s  dsh %s  node %s  端口 %d  %s  %s'
                         % (inst.label, inst.dsh_version or '?', inst.node_version or '?',
                            inst.port, STATUS_TEXT.get(inst.status(), inst.status()), inst.prefix))
        return '\n'.join(parts)

    # ------------------------------------------------------------ 列表/详情
    def _list_rows(self):
        """实例行的列表（桩 GTK 下 get_children() 不是可迭代对象，包一层）。"""
        try:
            return list(self.instance_list.get_children())
        except Exception:
            return []

    def refresh(self):
        keep = self.selected.prefix if self.selected is not None else None
        for child in self._list_rows():
            self.instance_list.remove(child)
        instances = self.manager.list_instances()
        self.lbl_count.set_text(str(len(instances)))
        target = None
        for inst in instances:
            row = self._instance_row(inst)
            self.instance_list.add(row)
            if keep and inst.prefix == keep:
                target = row
        self.instance_list.show_all()
        if target is not None:
            self.instance_list.select_row(target)
        elif instances:
            first = self.instance_list.get_row_at_index(0)
            if first is not None:
                self.instance_list.select_row(first)
        else:
            self.selected = None
            self.set_buttons_sensitive(False)
        try:
            self.lbl_footer_root.set_text('实例根目录 · %s' % self.manager.root)
        except Exception:
            pass

    def _instance_row(self, inst):
        row = Gtk.ListBoxRow()
        row.inst = inst
        row.get_style_context().add_class('instance-item')
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        initials = (inst.label or 'DS')[:2].upper()
        avatar = self._label(initials, 'instance-avatar')
        avatar.set_size_request(34, 34)
        box.pack_start(avatar, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        name = self._label(inst.label or inst.prefix, 'instance-name')
        name.set_ellipsize(3)
        text.pack_start(name, False, False, 0)
        sub = self._label('v%s' % (inst.dsh_version or '?'), 'instance-sub')
        text.pack_start(sub, False, False, 0)
        box.pack_start(text, True, True, 0)
        dot = self._label('', 'status-dot')
        dot.set_size_request(7, 7)
        box.pack_end(dot, False, False, 0)
        row.add(box)
        row.dot = dot
        row.sub = sub
        return row

    def on_row_selected(self, listbox, row):
        for child in self._list_rows():
            ctx = child.get_style_context()
            if child is row:
                ctx.add_class('active')
            else:
                ctx.remove_class('active')
        if row is None:
            self.selected = None
            self.set_buttons_sensitive(False)
            return
        inst = getattr(row, 'inst', None)
        if inst is None:
            return
        self.selected = self.manager.instance_at(inst.prefix)
        self._fill_details(self.selected)
        self.set_buttons_sensitive(True)

    def on_select(self, *_a):
        """兼容旧调用：把当前选择重新填一遍。"""
        if self.selected is not None:
            self._fill_details(self.selected)

    def _fill_details(self, inst):
        status = inst.status()
        pid = inst.running_pid()
        self.lbl_title.set_text(inst.label)
        self.lbl_crumb.set_text('实例概览')

        ctx = self.lbl_badge.get_style_context()
        for cls in ('running', 'needs-repair', 'stopped'):
            ctx.remove_class(cls)
        if status == 'running':
            ctx.add_class('running')
        elif status == 'broken':
            ctx.add_class('needs-repair')
        self.lbl_badge.set_text(STATUS_TEXT.get(status, status or '—'))

        self.lbl_avatar.set_text((inst.label or 'DS')[:2].upper())
        self.lbl_meta_name.set_text(inst.label or 'DeepSeek Harness')
        self.lbl_meta_path.set_text(inst.prefix)
        self.lbl_pill_dsh.set_text('dsh %s' % (inst.dsh_version or '?'))
        self.lbl_pill_node.set_text('Node %s' % (inst.node_version or '?'))
        self.lbl_metric_pid.set_text(str(pid) if pid else '—')
        self.lbl_metric_port.set_text(str(inst.port))
        self.lbl_metric_status.set_text(STATUS_TEXT.get(status, status or '—'))
        running = bool(pid)
        self.lbl_live.set_text('● 服务正常' if running else '● 未运行')

    def _tick(self):
        if self.busy:
            return True
        instances = {inst.prefix: inst for inst in self.manager.list_instances()}
        for child in self._list_rows():
            inst = instances.get(getattr(getattr(child, 'inst', None), 'prefix', ''))
            if inst is None:
                continue
            child.inst = inst
            ctx = child.dot.get_style_context()
            if inst.status() in ('stopped', 'broken'):
                ctx.add_class('stopped')
            else:
                ctx.remove_class('stopped')
            child.sub.set_text('v%s' % (inst.dsh_version or '?'))
        if self.selected is not None:
            fresh = self.manager.instance_at(self.selected.prefix)
            self.selected = fresh
            self._fill_details(fresh)
        return True

    # ------------------------------------------------------------ 日志
    def _push_recent_log(self, text):
        """把一行日志塞进「最近日志」卡（新的在上，最多 3 条）。"""
        import time as _time
        stamp = _time.strftime('%H:%M:%S')
        level, cls, body = '信息', 'info', text
        if text.startswith('✔'):
            level, cls, body = '成功', 'success', text[1:].strip()
        elif text.startswith('✘'):
            level, cls, body = '失败', 'danger', text[1:].strip()
        elif text.startswith('——') and text.rstrip().endswith('——'):
            level, cls, body = '系统', 'muted', text.strip('— ').strip()
        self._recent.insert(0, (stamp, level, cls, body[:180]))
        del self._recent[3:]
        try:
            self.lbl_log_count.set_text(str(len(self._recent)))
            for idx, (t, lvl, klass, msg) in enumerate(self._recent):
                t_lbl, lvl_lbl, msg_lbl = self.log_rows[idx]
                t_lbl.set_text(t)
                lvl_lbl.set_text(lvl)
                lctx = lvl_lbl.get_style_context()
                for name in ('success', 'info', 'muted', 'danger'):
                    lctx.remove_class(name)
                lctx.add_class(klass)
                msg_lbl.set_text(msg)
                msg_lbl.set_tooltip_text(msg)
        except Exception:
            pass

    def append_log(self, line, persist=True):
        text = (line or '').rstrip('\n')
        if not text:
            return
        end = self.log_buf.get_end_iter()
        self.log_buf.insert(end, text + '\n')
        if persist:
            append_manager_log(text)      # 同时落盘，供「查看完整日志」查看
        try:                                   # 裁剪只是防内存膨胀，失败不能影响日志本身
            limit = int(self.settings.get('logLines') or 800)
            count = self.log_buf.get_line_count()
            if count > limit + 200:
                cut = self.log_buf.get_iter_at_line(count - limit)
                self.log_buf.delete(self.log_buf.get_start_iter(), cut)
        except Exception:
            pass
        self._push_recent_log(text)

    def _drain_log(self):
        for line in self.manager.take_log():
            self.append_log(line)
        return True

    def set_buttons_sensitive(self, has_selection):
        for key, btn in self.buttons.items():
            if key in getattr(self, '_need_selection', set()):
                btn.set_sensitive(bool(has_selection) and not self.busy)
            else:
                btn.set_sensitive(not self.busy)
        if self.selected is not None:
            try:
                self.buttons['start'].set_sensitive(
                    not self.busy and self.selected.status() == 'stopped')
                self.buttons['stop'].set_sensitive(
                    not self.busy and bool(self.selected.running_pid()))
            except Exception:
                pass

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

        # 版本选择：预设版本号直接可用（原生下拉框 + 手动输入 + 各自一个「更新」按钮）。
        # 打开对话框时后台再拉一次联网列表，拉到就用新列表**覆盖**旧的。
        picker_dsh = VersionPicker(['latest'] + list(FALLBACK_DSH_VERSIONS), value='latest',
                                   fetcher=lambda: self.manager.available_dsh_versions(14),
                                   hint='或手动输入 dsh 版本，如 0.2.1-rc.5')
        picker_node = VersionPicker(['latest'] + list(FALLBACK_NODE_VERSIONS), value='latest',
                                    fetcher=lambda: self.manager.available_node_versions(),
                                    hint='或手动输入 Node 版本，如 26.13.0')

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
                ('dsh 版本', picker_dsh), ('Node 版本', picker_node)]
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
        dsh = picker_dsh.get_value() or 'latest'
        node = picker_node.get_value() or 'latest'
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
        """「管理器设置」不再是弹窗，而是设计稿里的第二页。"""
        self._show_page('settings')

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

        # 与「新建」一致：预设版本号直接可用；各自带「更新」按钮，打开时也后台拉一次
        picker_dsh = VersionPicker(['latest'] + list(FALLBACK_DSH_VERSIONS),
                                   value=inst.dsh_version or DEFAULT_DSH,
                                   fetcher=lambda: self.manager.available_dsh_versions(14),
                                   hint='或手动输入 dsh 版本')
        picker_node = VersionPicker(['latest'] + list(FALLBACK_NODE_VERSIONS),
                                    value=inst.node_version or DEFAULT_NODE,
                                    fetcher=lambda: self.manager.available_node_versions(),
                                    hint='或手动输入 Node 版本')

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
            dsh_list, node_list = [], []
            try:
                dsh_list = self.manager.available_dsh_versions(14) or []
            except Exception:
                pass
            try:
                node_list = self.manager.available_node_versions() or []
            except Exception:
                pass

            def apply():
                ver_state['done'] = True
                try:
                    ver_bar.hide()
                    if dsh_list or node_list:
                        ver_lbl.set_text('版本列表已就绪（latest = 最新的非 alpha 版本）')
                    else:
                        ver_lbl.set_text('联网获取失败，用的是预设版本号；也可以手动输入')
                    picker_dsh.set_options(['latest'] + [v for v in (dsh_list or []) if v != 'latest'])
                    picker_node.set_options(['latest'] + [v for v in (node_list or []) if v != 'latest'])
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
