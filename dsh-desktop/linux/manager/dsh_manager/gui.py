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
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

try:                      # 圆角裁切需要 cairo；没有就退回方形窗口
    import cairo
except ImportError:       # pragma: no cover
    cairo = None

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

# ---------------------------------------------------------------- 图标
# 设计稿的 27 个图标是 <symbol id="i-*"> 里的 24×24 描边路径，
# tools/extract-icons.mjs 已经把每个抽成 dsh_manager/icons/<name>.svg，
# 运行时只要把 currentColor 换成主题色，再让 GdkPixbuf 的 svg loader 画出来。
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
_ICON_CACHE = {}
_ICON_NAMES = set()
try:
    _ICON_NAMES = {f[:-4] for f in os.listdir(ICON_DIR) if f.endswith('.svg')}
except OSError:
    pass

# 旧代码里用的 Unicode 字形 → 设计稿图标名
GLYPH_ICON = {
    '＋': 'plus', '+': 'plus',
    '↗': 'external', 'ⓘ': 'info', '▶': 'arrow', '▣': 'copy', '⚒': 'wrench',
    '■': 'stop', '↺': 'refresh', '↻': 'restart', '▦': 'grid', '⚙': 'settings',
    '？': 'help', '⌄': 'chevron', '✓': 'check', '🗑': 'trash', '▤': 'terminal',
    '⟳': 'refresh', '○': 'info', '●': 'info',
}


def icon_pixbuf(name, color, px=16):
    """把 icons/<name>.svg 以指定颜色渲染成 px×px 的 pixbuf（带缓存）。"""
    key = (name, color, px)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    path = os.path.join(ICON_DIR, '%s.svg' % name)
    if not os.path.exists(path):
        _ICON_CACHE[key] = None
        return None
    with open(path, 'r', encoding='utf-8') as fh:
        svg = fh.read()
    svg = svg.replace('currentColor', color)
    # 先按 4 倍尺寸栅格化再缩，边缘更接近浏览器的抗锯齿效果
    big = max(px * 4, 32)
    svg = svg.replace('width="24"', 'width="%d"' % big, 1)
    svg = svg.replace('height="24"', 'height="%d"' % big, 1)
    try:
        loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
        loader.write(svg.encode('utf-8'))
        loader.close()
        pb = loader.get_pixbuf()
    except Exception as exc:                     # 没有 svg loader / 文件坏了
        sys.stderr.write('[dsh-manager] 图标 %s 渲染失败：%s\n' % (name, exc))
        pb = None
    if pb is not None and (pb.get_width() != px or pb.get_height() != px):
        pb = pb.scale_simple(px, px, GdkPixbuf.InterpType.BILINEAR)
    _ICON_CACHE[key] = pb
    return pb


def theme_tokens():
    """themes.json 的结构：{order, labels, values:{'frost-day': {accent: '#..', ...}}}。"""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'themes.json'),
                  'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def token_color(theme, mode, token):
    data = theme_tokens()
    combo = data.get('values', {}).get('%s-%s' % (theme, mode), {})
    return combo.get(token) or '#747288'



def _initials(label):
    """设计稿的头像文字：dsh→DS，deepseek-harness-1→D1，deepseek-harness-2→D2。

    规则：取第一段的首字母；末段是纯数字就用它，否则用第二段首字母。
    """
    text = (label or 'DS').strip()
    parts = [p for p in text.replace('_', '-').replace(' ', '-').split('-') if p]
    if not parts:
        return 'DS'
    head = parts[0][:1]
    if len(parts) > 1:
        if parts[-1].isdigit():
            return (head + parts[-1][:2]).upper()
        return (head + parts[1][:1]).upper()
    return text[:2].upper()


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
    _CURRENT.update({'theme': theme, 'mode': mode})
    try:
        ensure_extra_css(force=True)      # 主题色变了：底部按钮等自绘样式要重算
    except Exception:
        pass
    return True, theme, mode



_EXTRA_CSS = {'provider': None}
_CURRENT = {'theme': 'frost', 'mode': 'day'}


def _extra_css_text():
    """按当前主题令牌生成小皮肤（底部按钮对齐 Windows 的 BtnBase/Primary/DangerSoft）。"""
    theme = _CURRENT.get('theme') or 'frost'
    mode = _CURRENT.get('mode') or 'day'

    def tok(name, fallback):
        try:
            return token_color(theme, mode, name) or fallback
        except Exception:
            return fallback

    vals = {
        'text': tok('text', '#1a1a2e'),
        'card': tok('card', '#ffffff'),
        'card_solid': tok('card-solid', '#ffffff'),
        'inner': tok('inner-border', 'rgba(0,0,0,0.08)'),
        'accent': tok('accent', '#8b7cf6'),
        'accent2': tok('accent2', tok('accent', '#8b7cf6')),
        'on_accent': tok('on-accent', '#ffffff'),
        'danger': tok('danger', '#e35d6a'),
        'muted': tok('muted', '#6b6a7d'),
        'success': tok('success', '#2f9e6f'),
        'accent_soft': tok('accent-soft', 'rgba(139,124,246,0.18)'),
    }
    return (
        '.brand-logo { background-color: #ffffff; border-radius: 12px;'
        ' border: 1px solid rgba(0, 0, 0, 0.10); }\n'
        '.plugin-tree { font-size: 11px; }\n'
        '.plugin-thead { min-height: 22px; }\n'
        '.plugin-th { font-size: 10px; font-weight: bold; opacity: 0.7; }\n'
        '.foot-note { font-size: 10px; opacity: 0.75; }\n'
        '.foot-btn { min-height: 32px; min-width: 0; padding: 0 15px;'
        ' border-radius: 11px; font-size: 10px; font-weight: bold;'
        ' border-width: 1px; border-style: solid; border-color: %(inner)s;'
        ' background-image: none; background-color: %(card)s; color: %(text)s;'
        ' box-shadow: none; text-shadow: none; }\n'
        '.foot-btn:hover { background-color: %(card_solid)s; }\n'
        '.foot-btn.primary { border-width: 0; color: %(on_accent)s;'
        ' background-image: linear-gradient(135deg, %(accent2)s, %(accent)s);'
        ' background-color: %(accent)s; }\n'
        '.foot-btn.primary:hover { background-image:'
        ' linear-gradient(135deg, %(accent)s, %(accent2)s); }\n'
        '.foot-btn.danger { border-width: 0; color: %(danger)s;'
        ' background-image: none; background-color: alpha(%(danger)s, 0.14); }\n'
        '.foot-btn.danger:hover { background-color: alpha(%(danger)s, 0.22); }\n'
        '.plugin-thead { padding: 0; }\n'
        '.plugin-th { font-size: 10px; font-weight: bold; opacity: 0.7; }\n'
        '.plugin-id { font-size: 11px; font-weight: bold; }\n'
        '.plugin-desc { font-size: 11px; color: %(muted)s; }\n'
        '.plugin-status { font-size: 11px; }\n'
        '.plugin-status.ok { color: %(success)s; }\n'
        '.plugin-status.bad { color: %(danger)s; }\n'
        '.plugin-status.dim { color: %(muted)s; }\n'
        '.plugin-ver { font-size: 11px; font-family: monospace; color: %(muted)s; }\n'
        '.plugin-list row { padding: 0; margin: 2px 0; border-radius: 9px; }\n'
        '.plugin-list row:selected { background-color: %(accent_soft)s; }\n'
        '.plugin-row-body { padding: 13px 12px; border-radius: 9px; }\n'
        'entry, spinbutton { min-height: 32px; border-radius: 10px; padding: 4px 10px; }\n'
        '.dsh-dialog button { min-height: 32px; border-radius: 11px; padding: 0 15px; font-size: 10px; font-weight: bold; }\n'
        '.danger-card { margin-top: 16px; padding: 14px 16px; }\n'
        'button.danger { border-width: 0; color: %(danger)s;'
        ' background-image: none; background-color: alpha(%(danger)s, 0.14);'
        ' border-radius: 11px; min-height: 32px; padding: 0 15px;'
        ' font-size: 10px; font-weight: bold; }\n'
        'button.danger:hover { background-color: alpha(%(danger)s, 0.22); }\n'
        '.danger-title { font-size: 11px; font-weight: bold; }\n'
        '.danger-desc { font-size: 10px; color: %(muted)s; }\n'
        '.dlg-close, .dlg-close:hover, .dlg-close:focus { border: none;'
        ' box-shadow: none; background-image: none; background-color: transparent;'
        ' outline: none; }\n'
    ) % vals


def ensure_extra_css(force=False):
    """补几条主题文件里没有的规则（鲸鱼品牌块、对话框按钮）。

    主题 CSS 是生成出来的 14 个文件；只为一两个控件去改生成器不划算，
    这里挂一份独立小皮肤。颜色取自主题令牌 → 换主题/昼夜时重算（load_css 带 force=True 调）。
    """
    if _EXTRA_CSS['provider'] is not None and not force:
        return _EXTRA_CSS['provider']
    screen = Gdk.Screen.get_default()
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(_extra_css_text().encode('utf-8'))
        old = _EXTRA_CSS.get('provider')
        if old and screen is not None:
            try:
                Gtk.StyleContext.remove_provider_for_screen(screen, old)
            except Exception:
                pass
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        _EXTRA_CSS['provider'] = provider
    except Exception as exc:
        sys.stderr.write('[dsh-manager] 额外样式未加载：%s\n' % exc)
        _EXTRA_CSS['provider'] = False
    return _EXTRA_CSS['provider']
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
        .brand-logo {
            background-color: #ffffff;
            border-radius: 12px;
            border: 1px solid rgba(0, 0, 0, 0.10);
        }
        .plugin-tree { font-size: 11px; }
        .plugin-thead { min-height: 22px; }
        .plugin-th { font-size: 10px; font-weight: bold; opacity: 0.7; }
        .foot-note { font-size: 10px; opacity: 0.75; }
        .foot-btn {
            font-size: 10px;
            min-height: 32px;
            padding: 0 14px;
            border-radius: 16px;
        }
        """)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            # 用 USER 优先级：预览/主题 CSS 也是 USER，后加的生效，才盖得住按钮内边距
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        _EXTRA_CSS['provider'] = provider
    except Exception as exc:
        sys.stderr.write('[dsh-manager] 额外样式未加载：%s\n' % exc)
        _EXTRA_CSS['provider'] = False
    return _EXTRA_CSS['provider']


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



# ---------------------------------------------------------------- UI 看门狗
# 目的与 Windows 版一致：UI 卡死时能知道「卡之前用户做了什么」。
# 做法：GLib 每秒 tick 一次；后台线程发现超过 8 秒没 tick，就把最近 24 条操作写进 hang.log。
_HANG = {'last': 0.0, 'trail': [], 'started': False}


def hang_breadcrumb(text):
    try:
        import time as _t
        _HANG['trail'].append(_t.strftime('%H:%M:%S') + '  ' + str(text))
        if len(_HANG['trail']) > 24:
            del _HANG['trail'][:-24]
    except Exception:
        pass


def hang_log_path():
    return os.path.join(config_dir(), 'hang.log')


def start_hang_watchdog():
    """启动看门狗（幂等）。"""
    if _HANG.get('started'):
        return
    _HANG['started'] = True
    import threading
    import time as _t

    _HANG['last'] = _t.time()

    def tick():
        _HANG['last'] = _t.time()
        return True

    GLib.timeout_add(1000, tick)

    def loop():
        last_report = 0.0
        while True:
            _t.sleep(2)
            try:
                gap = _t.time() - _HANG['last']
                if gap < 8:
                    continue
                now = _t.time()
                if now - last_report < 10:
                    continue
                last_report = now
                lines = ['=== %s  UI 线程无响应 %ds ===' % (_t.strftime('%Y-%m-%d %H:%M:%S'), int(gap))]
                lines += ['  ' + x for x in _HANG['trail']]
                os.makedirs(config_dir(), exist_ok=True)
                with open(hang_log_path(), 'a', encoding='utf-8') as fh:
                    fh.write('\n'.join(lines) + '\n\n')
            except Exception:
                pass

    threading.Thread(target=loop, daemon=True, name='dsh-hang-watchdog').start()

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
        start_hang_watchdog()
        hang_breadcrumb('管理器窗口已就绪')



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
        # 窗口进程（WebKitGTK）据此决定页面的 prefers-color-scheme：
        # 只对本进程派生出来的窗口有效，不动系统设置。
        os.environ['DSH_DESKTOP_MODE'] = mode
        if persist and ok:
            save_settings({'theme': theme, 'mode': mode})
        self._sync_theme_labels(theme, mode)
        try:
            self._recolor_icons()
        except Exception:
            pass
        return ok

    def _sync_theme_labels(self, theme, mode):
        """把当前主题/模式写到界面各处（顶栏、设置页、菜单勾选）。"""
        index = theme_index()
        labels = index.get('labels', {}).get('%s-%s' % (theme, mode), [theme, mode])
        if getattr(self, 'lbl_theme_name', None) is not None:
            self.lbl_theme_name.set_text(labels[0])
        self._sync_mode_toggle(mode)
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
        labels = theme_index().get('labels', {}).get('%s-day' % theme, [theme])
        self._toast('主题已切换到「%s」' % labels[0])

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


    # ------------------------------------------------------------ 图标
    def _icon_for(self, glyph, role='muted', px=16):
        """字形 → 图标控件；没有对应图标时返回 None（调用方退回字形）。"""
        name = GLYPH_ICON.get(glyph) or (glyph if glyph in _ICON_NAMES else None)
        if not name:
            return None
        return self._icon(name, role, px)

    def _icon(self, name, role='muted', px=16):
        theme, mode = self._theme_state()
        color = token_color(theme, mode, role)
        pb = icon_pixbuf(name, color, px)
        if pb is None:
            lbl = Gtk.Label(label='·')
            return lbl
        img = Gtk.Image.new_from_pixbuf(pb)
        self._icons.append((img, name, role, px))
        return img

    def _recolor_icons(self):
        """换主题后按新配色重画所有图标。"""
        theme, mode = self._theme_state()
        for img, name, role, px in list(getattr(self, '_icons', [])):
            pb = icon_pixbuf(name, token_color(theme, mode, role), px)
            if pb is not None:
                try:
                    img.set_from_pixbuf(pb)
                except Exception:
                    pass
        try:
            self._sync_max_icon()          # 最大化/还原图标跟着主题色重画
        except Exception:
            pass

    # GTK3 的 EventBox 不把 CSS padding 算进尺寸（实测 allocation 完全一样），
    # 所以药丸的内边距必须做成内部 label 的 margin。数值取自 DESIGN_SPEC。
    CHIP_PAD = {
        'badge': (4, 9), 'subtle-tag': (3, 7), 'count-pill': (0, 6),
        'log-count': (1, 6), 'version-pill': (3, 7), 'live-text': (0, 0),
    }

    def _chip(self, text='', *classes, **kwargs):
        """带背景的小方块 / 圆点 / 徽标。

        关键点：GTK3 里 **label 不画背景**（1.3.0 的头像、状态点、药丸全都是"透明字"），
        要背景就得用会画 background 的容器。Gtk.EventBox 是 GTK3 里的标准做法。
        返回 EventBox，文字在 `chip.label`，尺寸用 width/height 参数固定。
        """
        box = Gtk.EventBox()
        box.set_visible_window(True)
        for cls in classes:
            box.get_style_context().add_class(cls)
        width = kwargs.get('width')
        height = kwargs.get('height')
        if not text and width and height and not kwargs.get('icon'):
            # 纯色块（状态点/圆点）：不能塞空 label —— 它的自然高度会把盒子撑成竖条
            lbl = Gtk.Label(label='')
            lbl.set_visible(False)
            box.label = lbl
            box.image = None
            box.set_size_request(width, height)
            box.set_valign(kwargs.get('valign') or Gtk.Align.CENTER)
            if kwargs.get('hexpand'):
                box.set_hexpand(True)
            return box
        if kwargs.get('icon'):
            img = self._icon(kwargs['icon'], kwargs.get('role', 'accent'),
                             kwargs.get('icon_size', 17))
            box.add(img)
            # EventBox 只能有一个子控件：图标块不再塞隐藏 label，
            # 但保留 .label 属性给外部代码（它们只会对文字 chip 调 set_text）。
            lbl = Gtk.Label(label='')
            lbl.set_visible(False)
        else:
            img = None
            lbl = Gtk.Label(label=text, xalign=0.5, yalign=0.5)
            box.add(lbl)
        box.image = img
        box.label = lbl
        pad = None
        for cls in classes:
            if cls in self.CHIP_PAD:
                pad = self.CHIP_PAD[cls]
                break
        if pad and not kwargs.get('width'):
            lbl.set_margin_top(pad[0])
            lbl.set_margin_bottom(pad[0])
            lbl.set_margin_start(pad[1])
            lbl.set_margin_end(pad[1])
        if width and height:
            box.set_size_request(width, height)
        # 不指定时默认居中：否则 EventBox 会填满父容器高度（计数胶囊被拉成竖条）
        box.set_valign(kwargs.get('valign') or Gtk.Align.CENTER)
        if kwargs.get('hexpand'):
            box.set_hexpand(True)
        return box

    def _button(self, key, label, *classes, **kwargs):
        """建按钮并登记到 self.buttons（set_buttons_sensitive 用）。"""
        btn = Gtk.Button()
        if kwargs.get('icon'):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
            role = kwargs.get('icon_role') or ('on-accent' if 'btn-primary' in classes
                                               else 'muted')
            widget = self._icon_for(kwargs['icon'], role, kwargs.get('icon_size', 16))
            if widget is not None:
                box.pack_start(widget, False, False, 0)
            else:
                box.pack_start(Gtk.Label(label=kwargs['icon']), False, False, 0)
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

    # ------------------------------------------------------------ 无边框窗口
    def _setup_frameless(self):
        """关掉系统标题栏，改用自绘窗口按钮 + 圆角裁切（可用环境变量退回系统标题栏）。"""
        self._frameless = os.environ.get('DSH_MANAGER_SYSTEM_TITLEBAR') != '1'
        self._maximized = False
        self._rgba = False
        if not self._frameless:
            self.set_decorated(True)    # 走 CSD：KWin 不画兜底应用图标
            return
        # 走 CSD：保留 decorated=True 但提供一个零高度自绘标题栏，
        # Wayland 会协商成 client-side，KWin 不画标题栏也不画兜底图标。
        self.set_decorated(True)
        # 窗口图标：任务栏/切换器用得到；也顺便观察它是不是右上角那个方块
        for icon_path in (os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                                      'share', 'dsh-desktop.png'),
                          '/usr/lib/dsh-manager/share/dsh-desktop.png',
                          '/usr/share/icons/hicolor/256x256/apps/dsh-manager.png'):
            try:
                if os.path.exists(icon_path):
                    self.set_icon_from_file(icon_path)
                    break
            except Exception:
                continue
        # 关键：给一个零高度的自绘标题栏，让 Wayland 协商成 CSD；
        # 否则 GTK 会退回服务端装饰，KWin 照样画标题栏。
        placeholder = Gtk.Box()
        placeholder.set_size_request(-1, 0)
        self.set_titlebar(placeholder)
        try:
            screen = Gdk.Screen.get_default()
            visual = screen.get_rgba_visual() if screen is not None else None
            if visual is not None and screen.is_composited():
                self.set_visual(visual)
                self.set_app_paintable(True)
                self._rgba = True
        except Exception:
            self._rgba = False
        if self._rgba and cairo is not None:
            self.connect('draw', self._on_window_draw)
        self.connect('window-state-event', self._on_window_state)

    def _corner_radius(self):
        """窗口圆角：跟主题的 app-radius；最大化时为 0。"""
        if self._maximized:
            return 0
        try:
            theme, mode = self._theme_state()
            value = str(token_color(theme, mode, 'app-radius') or '26px')
            return int(round(float(value.replace('px', ''))))
        except Exception:
            return 26

    @staticmethod
    def _rounded_path(cr, x, y, width, height, radius):
        if radius <= 0:
            cr.rectangle(x, y, width, height)
            return
        cr.new_sub_path()
        cr.arc(x + width - radius, y + radius, radius, -1.5708, 0)
        cr.arc(x + width - radius, y + height - radius, radius, 0, 1.5708)
        cr.arc(x + radius, y + height - radius, radius, 1.5708, 3.1416)
        cr.arc(x + radius, y + radius, radius, 3.1416, 4.7124)
        cr.close_path()

    def _window_bg_pixbuf(self):
        """当前主题的预渲染背景图（和 CSS 里 $(bg-image) 是同一张）。"""
        theme, mode = self._theme_state()
        key = '%s-%s' % (theme, mode)
        cached = getattr(self, '_bg_cache', None) or {}
        if key in cached:
            return cached[key]
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'backgrounds', '%s.png' % key)
        pb = None
        if os.path.exists(path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(path)
            except Exception:
                pb = None
        cached[key] = pb
        self._bg_cache = cached
        return pb

    def _on_window_draw(self, _widget, cr):
        """清透明（含四角）→ 圆角裁切 → 铺主题背景；子控件由默认处理器接着画。"""
        alloc = self.get_allocation()
        # 1) 整幅清成透明：圆角之外必须真的透出桌面
        cr.save()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.restore()
        # 2) 圆角裁切（这个 clip 要留给子控件，所以不能 restore 掉）
        self._rounded_path(cr, 0, 0, alloc.width, alloc.height, self._corner_radius())
        cr.clip()
        # 3) 自己画窗口背景：app_paintable 之后 GTK 不会替我们填
        pb = self._window_bg_pixbuf()
        if pb is not None and pb.get_width() > 0 and pb.get_height() > 0:
            cr.save()
            cr.scale(alloc.width / float(pb.get_width()),
                     alloc.height / float(pb.get_height()))
            Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
            cr.paint()
            cr.restore()
        return False

    def _on_window_state(self, _widget, event):
        maximized = bool(event.changed_mask & Gdk.WindowState.MAXIMIZED) and \
            bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)
        self._maximized = maximized
        shell = getattr(self, 'shell_box', None)
        if shell is not None:
            ctx = shell.get_style_context()
            if maximized:
                ctx.add_class('maximized')
            else:
                ctx.remove_class('maximized')
        self.queue_draw()
        return False

    def _start_window_drag(self, widget, event):
        """顶栏空白处拖动窗口；双击切最大化。按钮等子控件会自己吃掉事件。"""
        if not getattr(self, '_frameless', False):
            return False
        if event.button != 1:
            return False
        # GDK 的双击事件名带前导下划线（_2BUTTON_PRESS），不同绑定版本暴露方式不一，
        # 用 getattr 取，取不到就退化成只支持拖动。
        double = getattr(Gdk.EventType, '_2BUTTON_PRESS', None)
        if double is not None and event.type == double:
            self._toggle_maximize()
            return True
        try:
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            return True
        except Exception:
            return False

    def _toggle_maximize(self):
        if self.is_maximized():
            self.unmaximize()
        else:
            self.maximize()

    def _window_buttons(self):
        """右上角三个自绘窗口按钮（最小化 / 最大化-还原 / 关闭）。"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        box.get_style_context().add_class('window-buttons')
        box.set_valign(Gtk.Align.CENTER)
        self.btn_win_min = self._window_button('minus', '最小化', self.iconify)
        self.btn_win_max = self._window_button('maximize', '最大化', self._toggle_maximize)
        self.btn_win_close = self._window_button('x', '关闭', self.close)
        self.btn_win_close.get_style_context().add_class('window-close')
        box.pack_start(self.btn_win_min, False, False, 0)
        box.pack_start(self.btn_win_max, False, False, 0)
        box.pack_start(self.btn_win_close, False, False, 0)
        self._refresh_window_icons()   # 三个图标按当前主题色先画一次
        return box

    def _window_button(self, icon, tooltip, handler):
        btn = Gtk.Button()
        btn.get_style_context().add_class('window-btn')
        btn.set_size_request(32, 32)
        btn.set_valign(Gtk.Align.CENTER)
        img = Gtk.Image()
        btn.add(img)
        btn._img = img
        btn._icon_name = icon
        btn.set_tooltip_text(tooltip)
        btn.connect('clicked', lambda *a: handler())
        btn.set_relief(Gtk.ReliefStyle.NONE)
        return btn

    def _refresh_window_icons(self):
        """按当前主题色重画三个窗口图标（最小化/最大化-还原/关闭）。"""
        theme, mode = self._theme_state()
        color = token_color(theme, mode, 'muted')
        for btn in (getattr(self, 'btn_win_min', None),
                    getattr(self, 'btn_win_max', None),
                    getattr(self, 'btn_win_close', None)):
            if btn is None:
                continue
            img = getattr(btn, '_img', None)
            if img is None:
                continue
            pb = icon_pixbuf(getattr(btn, '_icon_name', 'x'), color, 16)
            if pb is not None:
                img.set_from_pixbuf(pb)

    def _sync_max_icon(self):
        """最大化后把"最大化"图标换成"还原"（只换 pixbuf，不动子控件）。"""
        btn = getattr(self, 'btn_win_max', None)
        if btn is None:
            return
        btn._icon_name = 'restore' if self.is_maximized() else 'maximize'
        btn.set_tooltip_text('还原' if self.is_maximized() else '最大化')
        theme, mode = self._theme_state()
        pb = icon_pixbuf(btn._icon_name, token_color(theme, mode, 'muted'), 16)
        if pb is not None and getattr(btn, '_img', None) is not None:
            btn._img.set_from_pixbuf(pb)

    def _build(self):
        self.buttons = {}
        self._need_selection = {'start', 'stop', 'open', 'reload', 'rebuild', 'token',
                                'folder', 'uninstall', 'plugins', 'update', 'repair'}
        self._theme_buttons = {}
        self._icons = []
        self._recent = []
        # 完整日志只存缓冲区（界面上的「最近日志」只显示 3 行；完整内容走对话框）
        self.log_buf = Gtk.TextBuffer()
        self.set_titlebar(None)
        self.get_style_context().add_class('dsh-window')
        self._setup_frameless()

        toast = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toast.get_style_context().add_class('toast')
        toast.pack_start(self._chip('✓', 'toast-icon', width=18, height=18), False, False, 0)
        self.lbl_toast = self._label('操作已完成', 'toast-text')
        toast.pack_start(self.lbl_toast, False, False, 0)
        self.toast_revealer = Gtk.Revealer()
        self.toast_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.toast_revealer.set_halign(Gtk.Align.CENTER)
        self.toast_revealer.set_valign(Gtk.Align.END)
        self.toast_revealer.set_margin_bottom(35)   # 设计稿 .toast{bottom:35px}
        self.toast_revealer.add(toast)
        self.toast_revealer.set_reveal_child(False)

        overlay = Gtk.Overlay()
        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        shell.get_style_context().add_class('dsh-shell')
        # 设计稿里 .app-shell 就是"窗口"本身：参考图裁的就是它，所以不能留外边距，
        # 否则整体会内缩 18px，和设计稿错位（实测 MAE 就是被这 18px 抬上去的）。
        shell.set_margin_top(0)
        shell.set_margin_bottom(0)
        shell.set_margin_start(0)
        shell.set_margin_end(0)
        overlay.add(shell)
        overlay.add_overlay(self.toast_revealer)
        self.add(overlay)

        self.shell_box = shell        # 断点判定与 CSS 类都挂在这里
        shell.pack_start(self._build_sidebar(), False, False, 0)
        shell.pack_start(self._build_main(), True, True, 0)

        # 忙碌指示条：放在顶栏下面，不打断布局
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

        self.shell_box.connect('size-allocate', self._on_size_allocate)
        self.connect('size-allocate', self._on_size_allocate)
        GLib.timeout_add(300, lambda: (self._apply_breakpoints(force=True), False)[1])
        self.set_buttons_sensitive(False)

    def _whale_mark(self, px=38):
        """品牌标：白底圆角方 + 黑色鲸鱼（和 Windows 版侧栏、程序图标同一只）。"""
        ensure_extra_css()
        box = Gtk.EventBox()
        box.set_visible_window(True)
        box.get_style_context().add_class('brand-logo')
        box.set_size_request(px, px)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons', 'whale.png')
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, px - 12, px - 12, True)
            box.add(Gtk.Image.new_from_pixbuf(pb))
        except Exception:
            box.add(self._label('D', 'brand-mark-text'))
        return box

    # ---- 侧栏 ----
    def _build_sidebar(self):
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        side.get_style_context().add_class('sidebar')
        side.set_size_request(248, -1)
        self.sidebar_box = side        # 断点里会切成 220

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        # 设计稿 .brand{padding:0 8px 28px}
        brand.set_margin_bottom(28)
        brand.set_margin_start(8)
        brand.set_margin_end(8)
        brand.pack_start(self._whale_mark(38), False, False, 0)
        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        brand_text.pack_start(self._label('DeepSeek Harness', 'brand-title'), False, False, 0)
        brand_text.pack_start(self._label('管理器 v%s' % MANAGER_VERSION, 'brand-sub'),
                              False, False, 0)
        brand.pack_start(brand_text, False, False, 0)
        side.pack_start(brand, False, False, 0)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        head.get_style_context().add_class('side-section-title')
        head.pack_start(self._label('我的实例', 'side-section-title'), False, False, 0)
        self.chip_count = self._chip('0', 'count-pill')
        head.pack_start(self.chip_count, False, False, 0)
        head.set_size_request(-1, 32)
        head.set_margin_bottom(7)   # 左右留白交给 CSS 的 padding（设计稿 .side-section-title）
        # 对齐 Windows：这里原来是「＋新建实例」，现在是「刷新实例列表」
        # （新建实例另有下面那个大按钮，重复的「＋」没必要）
        self._refresh_stack = Gtk.Stack()
        self._refresh_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._refresh_icon = self._icon('refresh', 'muted', 15)
        self._refresh_spin = Gtk.Spinner()
        self._refresh_stack.add_named(self._refresh_icon, 'icon')
        self._refresh_stack.add_named(self._refresh_spin, 'spin')
        self._refresh_stack.set_visible_child_name('icon')
        self.btn_refresh_side = Gtk.Button()
        self.btn_refresh_side.get_style_context().add_class('icon-btn')
        self.btn_refresh_side.get_style_context().add_class('small')
        self.btn_refresh_side.set_tooltip_text('刷新实例列表')
        self.btn_refresh_side.add(self._refresh_stack)
        self.btn_refresh_side.connect('clicked', self.on_refresh_list)
        head.pack_end(self.btn_refresh_side, False, False, 0)
        side.pack_start(head, False, False, 0)

        self.instance_list = Gtk.ListBox()
        self.instance_list.get_style_context().add_class('instance-list')
        self.instance_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.instance_list.connect('row-selected', self.on_row_selected)
        self.side_sw = Gtk.ScrolledWindow()
        self.side_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.side_sw.add(self.instance_list)
        # 设计稿里实例列表是**按内容高**（3×61 + 2×5 = 193），下面紧接「新建实例」，
        # 剩下的空白留给侧栏底部；所以这里不 vexpand，改用一个弹簧撑住底部块。
        side.pack_start(self.side_sw, False, False, 0)

        btn_new = self._button('new', '＋  新建实例', 'new-instance')
        btn_new.set_size_request(-1, 38)
        btn_new.set_margin_top(13)
        btn_new.set_margin_start(4)
        btn_new.set_margin_end(4)
        side.pack_start(btn_new, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        side.pack_start(spacer, True, True, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bottom.set_margin_top(24)
        bottom.pack_start(self._label('工作空间', 'side-caption'), False, False, 0)
        self.btn_overview = self._button('', '实例概览', 'side-link', 'selected',
                                         handler=lambda *a: self._show_page('dashboard'),
                                         icon='grid', icon_role='accent', icon_size=17)
        bottom.pack_start(self.btn_overview, False, False, 0)
        self.btn_settings = self._button('settings', '管理器设置', 'side-link',
                                         icon='settings', icon_role='muted', icon_size=17)
        bottom.pack_start(self.btn_settings, False, False, 0)
        self.btn_help = self._button('', '使用帮助', 'side-link', handler=self.on_help,
                                    icon='help', icon_role='muted', icon_size=17)
        bottom.pack_start(self.btn_help, False, False, 0)

        runtime = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        runtime.get_style_context().add_class('runtime')
        runtime.set_margin_top(17)
        runtime.set_margin_start(4)
        runtime.set_margin_end(4)
        runtime.set_size_request(-1, 56)
        runtime.set_valign(Gtk.Align.CENTER)
        runtime.pack_start(self._chip('Py', 'runtime-icon', width=28, height=28), False, False, 0)
        rt_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        rt_text.pack_start(self._label('运行环境正常', 'runtime-title'), False, False, 0)
        self.lbl_runtime = self._label(
            'Python %s · GTK %s' % (sys.version.split()[0], gtk_ver), 'runtime-sub')
        rt_text.pack_start(self.lbl_runtime, False, False, 0)
        runtime.pack_start(rt_text, True, True, 0)
        runtime.pack_start(self._chip('', 'status-dot', width=7, height=7, valign=Gtk.Align.CENTER),
                           False, False, 0)
        bottom.pack_start(runtime, False, False, 0)
        side.pack_start(bottom, False, False, 0)
        return side

    # ---- 主区 ----
    def _build_main(self):
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_box.pack_start(self._build_topbar(), False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(160)
        self.stack.add_named(self._build_dashboard(), 'dashboard')
        self.stack.add_named(self._build_settings_page(), 'settings')
        self.main_box.pack_start(self.stack, True, True, 0)
        return self.main_box


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
        shell = getattr(self, 'shell_box', None)
        width = shell.get_allocated_width() if shell is not None else 0
        height = shell.get_allocated_height() if shell is not None else 0
        if width <= 1 or height <= 1:            # 还没完成布局，用窗口尺寸兜底
            width = self.get_allocated_width()
            height = self.get_allocated_height()
        if width <= 1 or height <= 1:
            return
        narrow = width <= 1280
        short = height <= 850
        if not force and (narrow, short) == getattr(self, '_bp', None):
            return
        self._bp = (narrow, short)

        ctx = (shell or self).get_style_context()
        for cls, on in (('narrow', narrow), ('short', short)):
            if on:
                ctx.add_class(cls)
            else:
                ctx.remove_class(cls)

        # ① 侧栏 220 / 248
        side = getattr(self, 'sidebar_box', None)
        if side is not None:
            side.set_size_request(220 if narrow else 248, -1)

        # ② 快捷功能固定四列（用户要求一排四个；设计稿 §2.5 的窄屏两列不再采用）
        self._rebuild_quick_grid(4)

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

    def _build_topbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bar.get_style_context().add_class('topbar')

        crumb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        crumb.pack_start(self._label('工作空间', 'breadcrumb'), False, False, 0)
        crumb.pack_start(self._label('/', 'breadcrumb'), False, False, 0)
        self.lbl_crumb = self._label('实例概览', 'breadcrumb-current')
        crumb.pack_start(self.lbl_crumb, False, False, 0)
        bar.pack_start(crumb, False, False, 0)

        trigger = Gtk.MenuButton()
        trigger.get_style_context().add_class('theme-trigger')
        trigger.set_valign(Gtk.Align.CENTER)
        trigger.set_size_request(-1, 34)   # 设计稿 .theme-trigger 高 34
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        inner.pack_start(self._chip('', 'theme-swatch', 'swatch-frost', width=14, height=14,
                                    valign=Gtk.Align.CENTER), False, False, 0)
        self.lbl_theme_name = self._label('毛玻璃')
        inner.pack_start(self.lbl_theme_name, False, False, 0)
        inner.pack_start(self._icon('chevron', 'muted', 14), False, False, 0)
        trigger.add(inner)

        popover = Gtk.Popover()
        popover.get_style_context().add_class('theme-menu')
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        menu.set_size_request(215, -1)   # 设计稿 .more-menu 宽 215
        menu.set_border_width(7)
        menu.pack_start(self._label('选择界面主题', 'menu-header'), False, False, 0)
        index = theme_index()
        for key in index.get('order', []):
            labels = index.get('labels', {}).get('%s-day' % key, [key, ''])
            row = Gtk.Button()
            row.get_style_context().add_class('flat')
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
            box.pack_start(self._chip('', 'theme-dot', 'swatch-%s' % key, width=12, height=12,
                                      valign=Gtk.Align.CENTER), False, False, 0)
            name = Gtk.Label(label=labels[0], xalign=0.0)
            name.set_width_chars(10)
            box.pack_start(name, False, False, 0)
            box.pack_end(self._label(labels[1], 'theme-hint'), False, False, 0)
            row.add(box)
            row.theme_key = key
            row.connect('clicked', self.on_pick_theme)
            menu.pack_start(row, False, False, 0)
            self._theme_buttons[key] = row
        popover.add(menu)
        trigger.set_popover(popover)
        self._theme_popover = popover

        self.btn_mode = self._build_mode_toggle()
        self.btn_mode.set_valign(Gtk.Align.CENTER)
        info = self._button('', 'ⓘ', 'icon-btn', handler=self.on_about)
        info.set_tooltip_text('关于 / 版本信息')
        # 设计稿的右半区顺序是：主题触发器 → 日夜开关 → 分隔线 → 信息按钮。
        # pack_end 的插入顺序反直觉（后加的会挤到左边），所以用一个横向容器把
        # 顺序写死，再整体 pack_end 一次。
        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        right.set_valign(Gtk.Align.CENTER)
        right.pack_start(trigger, False, False, 0)
        right.pack_start(self.btn_mode, False, False, 0)
        divider = Gtk.Box()
        divider.get_style_context().add_class('top-divider')
        divider.set_size_request(1, 20)
        divider.set_valign(Gtk.Align.CENTER)
        right.pack_start(divider, False, False, 0)
        right.pack_start(info, False, False, 0)
        if getattr(self, '_frameless', False):
            sep2 = Gtk.Box()
            sep2.get_style_context().add_class('top-divider')
            sep2.set_size_request(1, 20)
            sep2.set_valign(Gtk.Align.CENTER)
            right.pack_start(sep2, False, False, 0)
            right.pack_start(self._window_buttons(), False, False, 0)
        bar.pack_end(right, False, False, 0)
        bar.connect('button-press-event', self._start_window_drag)
        bar.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect_after('window-state-event',
                           lambda *a: (self._sync_max_icon(), False)[1])
        return bar


    # ------------------------------------------------------------ 日夜开关
    def _build_mode_toggle(self):
        """设计稿的 .mode-toggle：太阳/月亮两个图标 + 一个圆滑块。"""
        btn = Gtk.Button()
        btn.get_style_context().add_class('mode-toggle')
        btn.connect('clicked', self.on_toggle_mode)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.set_homogeneous(True)
        self.icon_mode_sun = self._icon('sun', 'accent', 14)
        self.icon_mode_moon = self._icon('moon', 'muted', 14)
        row.pack_start(self.icon_mode_sun, True, True, 0)
        row.pack_start(self.icon_mode_moon, True, True, 0)

        thumb = Gtk.EventBox()
        thumb.set_visible_window(True)
        thumb.get_style_context().add_class('mode-thumb')
        thumb.set_size_request(22, 22)
        thumb.set_valign(Gtk.Align.CENTER)
        thumb.set_halign(Gtk.Align.START)
        thumb.set_margin_start(3)
        self.chip_mode_thumb = thumb

        overlay = Gtk.Overlay()
        overlay.add(row)
        overlay.add_overlay(thumb)
        btn.add(overlay)
        return btn

    def _sync_mode_toggle(self, mode):
        """滑块靠 halign+margin 换边（GTK3 没有 transform:translateX）。"""
        thumb = getattr(self, 'chip_mode_thumb', None)
        if thumb is not None:
            if mode == 'night':
                thumb.set_halign(Gtk.Align.END)
                thumb.set_margin_start(0)
                thumb.set_margin_end(3)
            else:
                thumb.set_halign(Gtk.Align.START)
                thumb.set_margin_end(0)
                thumb.set_margin_start(3)
        sun = getattr(self, 'icon_mode_sun', None)
        moon = getattr(self, 'icon_mode_moon', None)
        if sun is not None:
            sun.set_opacity(0.5 if mode == 'night' else 1.0)
        if moon is not None:
            moon.set_opacity(1.0 if mode == 'night' else 0.55)

    def _build_dashboard(self):
        self.dash_sw = Gtk.ScrolledWindow()
        # 布局是按设计稿 1392 宽钉死的；窗口更窄时给横向滚动条，别把右半边裁掉。
        self.dash_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.get_style_context().add_class('content')
        # 设计稿 .content{padding:25px 30px 15px} —— 用 CSS padding，盒子本身仍是满宽
        self.dash_sw.add(page)

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        heading.set_margin_bottom(18)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        _eyebrow = self._label('INSTANCE OVERVIEW', 'eyebrow')
        _eyebrow.set_halign(Gtk.Align.START)
        text.pack_start(_eyebrow, False, False, 0)
        title_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.lbl_title = self._label('选择左侧的实例', 'page-title')
        title_line.pack_start(self.lbl_title, False, False, 0)
        # 设计稿 .status-badge = 5px 圆点 + 5px 间距 + 文字；圆点颜色随 running/stopped
        badge = Gtk.EventBox()
        badge.set_visible_window(True)
        badge.get_style_context().add_class('badge')
        badge.set_valign(Gtk.Align.CENTER)
        badge_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        # EventBox 的 CSS padding 不算尺寸，内边距只能落在子控件的 margin 上
        badge_inner.set_margin_top(4)
        badge_inner.set_margin_bottom(4)
        badge_inner.set_margin_start(9)
        badge_inner.set_margin_end(9)
        badge_inner.pack_start(self._chip('', 'badge-dot', width=5, height=5,
                                          valign=Gtk.Align.CENTER), False, False, 0)
        self.lbl_badge = self._label('—', 'badge-text')
        badge_inner.pack_start(self.lbl_badge, False, False, 0)
        badge.add(badge_inner)
        badge.label = self.lbl_badge
        self.chip_badge = badge
        title_line.pack_start(self.chip_badge, False, False, 0)
        text.pack_start(title_line, False, False, 0)
        self.lbl_page_desc = self._label('管理服务、窗口与扩展，让实例始终保持最佳状态。',
                                        'page-desc')
        text.pack_start(self.lbl_page_desc, False, False, 0)
        heading.pack_start(text, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_valign(Gtk.Align.CENTER)
        # 窗口功能：会话窗口里那些「我们自己加的小功能」的开关（对齐 Windows）
        self.btn_features = self._button('features', '窗口功能', 'btn', 'btn-secondary',
                                         icon='info', icon_size=15,
                                         handler=self.on_window_features)
        actions.pack_start(self.btn_features, False, False, 0)
        self.btn_open = self._button('open', '打开窗口', 'btn', 'btn-primary', icon='↗')
        actions.pack_start(self.btn_open, False, False, 0)
        more = Gtk.MenuButton()
        more.set_valign(Gtk.Align.CENTER)
        more.get_style_context().add_class('btn')
        more.get_style_context().add_class('btn-secondary')
        more.get_style_context().add_class('btn-icon')
        more.add(self._icon('more', 'muted', 16))   # 设计稿 i-more（三个实心圆点）
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

        grid = Gtk.Grid(column_spacing=16, row_spacing=16)
        info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        info_card.get_style_context().add_class('card')
        info_card.get_style_context().add_class('instance-card')
        info_card.set_hexpand(True)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top.pack_start(self._label('实例信息', 'card-label'), False, False, 0)
        top.pack_end(self._chip('本地实例', 'subtle-tag', valign=Gtk.Align.CENTER),
                     False, False, 0)
        info_card.pack_start(top, False, False, 0)
        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=13)
        meta.set_margin_top(17)
        self.chip_avatar = self._chip('--', 'large-avatar', width=48, height=48,
                                      valign=Gtk.Align.CENTER)
        meta.pack_start(self.chip_avatar, False, False, 0)
        meta_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.lbl_meta_name = self._label('—', 'meta-name')
        meta_text.pack_start(self.lbl_meta_name, False, False, 0)
        self.lbl_meta_path = self._label('—', 'meta-path')
        self.lbl_meta_path.set_selectable(True)
        meta_text.pack_start(self.lbl_meta_path, False, False, 0)
        pills = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pills.set_margin_top(4)
        self.chip_pill_dsh = self._chip('dsh —', 'version-pill')
        self.chip_pill_node = self._chip('Node —', 'version-pill')
        pills.pack_start(self.chip_pill_dsh, False, False, 0)
        pills.pack_start(self.chip_pill_node, False, False, 0)
        meta_text.pack_start(pills, False, False, 0)
        meta.pack_start(meta_text, True, True, 0)
        info_card.pack_start(meta, False, False, 0)
        sep = Gtk.Separator()
        sep.set_margin_top(18)
        info_card.pack_start(sep, False, False, 0)
        metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        metrics.get_style_context().add_class('metric-row')
        metrics.set_margin_top(13)
        self.lbl_metric_pid = self._metric(metrics, '进程 PID', '—', first=True)
        metrics.pack_start(self._vsep(), False, False, 0)
        self.lbl_metric_port = self._metric(metrics, '服务端口', '—')
        metrics.pack_start(self._vsep(), False, False, 0)
        self.lbl_metric_status = self._metric(metrics, '运行状态', '—', accent=True)
        info_card.pack_start(metrics, False, False, 0)

        control = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        control.get_style_context().add_class('card')
        control.get_style_context().add_class('control-card')
        control.set_size_request(402, -1)   # 高度交给 CSS（205 含 padding）
        self.control_card = control
        ctop = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ctop.pack_start(self._label('快捷控制', 'card-label'), False, False, 0)
        live = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        live.get_style_context().add_class('live-indicator')
        self.chip_live_dot = self._chip('', 'live-dot', width=5, height=5,
                                        valign=Gtk.Align.CENTER)
        live.pack_start(self.chip_live_dot, False, False, 0)
        self.lbl_live = self._label('服务正常', 'live-text')
        live.pack_start(self.lbl_live, False, False, 0)
        self.chip_live = live
        ctop.pack_end(self.chip_live, False, False, 0)
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

        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        section.set_margin_top(18)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        head.pack_start(self._label('常用功能', 'section-title'), False, False, 0)
        head.pack_start(self._label('管理实例的扩展与文件', 'section-sub'), False, False, 0)
        section.pack_start(head, False, False, 0)
        self._quick_specs = (
            ('token', '查看 Token', '访问凭证与连接信息', 'key'),
            ('plugins', '管理插件', '安装、启用与配置扩展', 'puzzle'),
            ('update', '检查更新', '获取最新的 dsh 与 Node', 'update'),
            ('folder', '数据目录', '浏览配置与本地数据', 'folder'))
        self.quick_grid = Gtk.Grid(column_spacing=11, row_spacing=11)
        self.quick_grid.set_column_homogeneous(True)
        self._quick_cols = 0
        self._rebuild_quick_grid(4)
        section.pack_start(self.quick_grid, False, False, 0)
        self.quick_section = section
        page.pack_start(section, False, False, 0)

        log_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        log_card.get_style_context().add_class('card')
        log_card.get_style_context().add_class('log-card')   # .log-card{padding:0}
        # 顶部留白交给 CSS 的 .log-card{margin-top:20px}；这里再设一次会叠加成 40px
        log_card.set_margin_top(0)
        lhead = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lhead.get_style_context().add_class('log-header')
        lhead.pack_start(self._icon('terminal', 'accent', 15), False, False, 0)
        lhead.pack_start(self._label('最近日志', 'log-title'), False, False, 0)
        self.chip_log_count = self._chip('0', 'log-count')
        lhead.pack_start(self.chip_log_count, False, False, 0)
        view_btn = self._button('', '查看完整日志', 'text-btn', handler=self.on_view_log,
                                icon='arrow', icon_role='accent', icon_size=12)
        lhead.pack_end(view_btn, False, False, 0)
        log_card.pack_start(lhead, False, False, 0)
        # 设计稿 .log-body{padding:7px 18px 9px}，行间没有额外间距；
        # 原来 spacing=6 + margin_top=8 让日志卡比设计稿高 20px。
        self.log_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.log_body.get_style_context().add_class('log-body')
        self.log_rows = []
        self.lbl_log_empty = self._label('还没有日志', 'log-empty')
        # 空态要能被"有日志"盖掉；但任何 show_all() 都会把隐藏控件重新显示出来，
        # 所以这里声明 no_show_all，可见性只由 _push_recent_log 控制。
        self.lbl_log_empty.set_no_show_all(True)
        self.log_body.pack_start(self.lbl_log_empty, False, False, 0)
        self.lbl_log_empty.show()      # no_show_all 之后要自己显一次（首屏就是空态）
        # 与 Windows 对齐：最近日志最多 15 条（空行先建好、隐藏，来一条显示一条）
        for _ in range(15):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
            t = self._label('', 'log-time')
            lvl = self._chip('', 'log-level')
            msg = self._label('', 'log-line')
            msg.set_ellipsize(3)
            row.pack_start(t, False, False, 0)
            row.pack_start(lvl, False, False, 0)
            row.pack_start(msg, True, True, 0)
            self.log_body.pack_start(row, False, False, 0)
            row.hide()
            self.log_rows.append((t, lvl, msg, row))
        log_card.pack_start(self.log_body, False, False, 0)
        page.pack_start(log_card, False, False, 0)

        # ---- 删除实例（对齐 Windows：仪表盘最下方一张卡）----
        del_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        del_card.get_style_context().add_class('card')
        del_card.get_style_context().add_class('danger-card')
        del_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        del_head.get_style_context().add_class('danger-head')
        del_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        del_text.pack_start(self._label('删除实例', 'danger-title'), False, False, 0)
        self.lbl_del_hint = self._label('停止服务并删除该实例的安装目录（只对管理器创建的实例生效）',
                                        'danger-desc')
        del_text.pack_start(self.lbl_del_hint, False, False, 0)
        del_head.pack_start(del_text, True, True, 0)
        self.btn_delete_instance = self._button('trash', '删除实例', 'danger', icon_role='danger',
                                                icon_size=14, handler=self.on_delete_instance)
        self.btn_delete_instance.set_size_request(-1, 32)
        del_head.pack_end(self.btn_delete_instance, False, False, 0)
        del_card.pack_start(del_head, False, False, 0)
        page.pack_start(del_card, False, False, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        # 设计稿里 .page-footer 是"整行容器 + space-between"，所以样式类要挂在容器上，
        # 而不是两个标签上（否则量出来的宽度只有文字那么宽）。
        footer.get_style_context().add_class('page-footer')
        footer.pack_start(self._label('●  所有更改已自动保存', 'footer-text'), False, False, 0)
        self.lbl_footer_root = self._label('实例根目录 · %s' % self.manager.root, 'footer-text')
        footer.pack_end(self.lbl_footer_root, False, False, 0)
        footer.set_hexpand(True)
        self.dash_footer = footer
        page.pack_start(footer, False, False, 0)
        return self.dash_sw

    def _vsep(self):
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.get_style_context().add_class('metric-sep')
        return sep

    def _metric(self, parent, label, value, first=False, accent=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.set_hexpand(True)
        box.set_margin_start(0 if first else 12)
        box.set_margin_end(12)
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
        icon_name = glyph if glyph in _ICON_NAMES else GLYPH_ICON.get(glyph)
        btn = Gtk.Button()
        btn.get_style_context().add_class('quick-action')
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.pack_start(self._chip('', 'quick-icon', width=34, height=34,
                                  valign=Gtk.Align.CENTER, icon=icon_name,
                                  role='accent', icon_size=17), False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text.pack_start(self._label(title, 'quick-title'), False, False, 0)
        sub_lbl = self._label(sub, 'quick-sub')
        sub_lbl.set_ellipsize(3)
        text.pack_start(sub_lbl, False, False, 0)
        box.pack_start(text, True, True, 0)
        box.pack_end(self._label('→', 'quick-arrow'), False, False, 0)
        btn.add(box)
        self.buttons[key] = btn
        handler = getattr(self, 'on_' + key, None)
        if handler is not None:
            btn.connect('clicked', handler)
        return btn

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
        self.chip_count.label.set_text(str(len(instances)))
        target = None
        for inst in instances:
            row = self._instance_row(inst)
            self.instance_list.add(row)
            if keep and inst.prefix == keep:
                target = row
        last = self._list_rows()
        if last:
            last[-1].set_margin_bottom(0)
        self.instance_list.show_all()
        # ScrolledWindow 不给最小内容高就只分到 41px，列表被裁掉只剩第一行
        try:
            rows = max(1, len(instances))
            self.side_sw.set_min_content_height(min(rows, 6) * 66 - 5)
        except Exception:
            pass
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
            # 刷新后把内容滚回顶部：否则标题区会被顶栏压住（实测过）
            adj = self.dash_sw.get_vadjustment()
            if adj is not None:
                adj.set_value(0)
        except Exception:
            pass

    @staticmethod
    def _row_sub(inst):
        """实例行第二行：dsh 版本 · 端口 · PID（对齐 Windows 版的信息密度）。"""
        parts = ['dsh %s' % (inst.dsh_version or '?')]
        pid = 0
        try:
            pid = int(inst.running_pid() or 0)
        except Exception:
            pid = 0
        parts.append(('PID %d' % pid) if pid else '已停止')
        return ' · '.join(parts)

    def _instance_row(self, inst):
        row = Gtk.ListBoxRow()
        row.inst = inst
        row.get_style_context().add_class('instance-item')
        # 设计稿：.instance-item{height:61px; gap:5px}
        row.set_size_request(-1, 61)
        row.set_margin_bottom(5)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        initials = _initials(inst.label)
        box.pack_start(self._chip(initials, 'instance-avatar', width=34, height=34,
                                  valign=Gtk.Align.CENTER),
                       False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        name = self._label(inst.label or inst.prefix, 'instance-name')
        name.set_ellipsize(3)
        text.pack_start(name, False, False, 0)
        sub = self._label(self._row_sub(inst), 'instance-sub')
        sub.set_ellipsize(3)
        text.pack_start(sub, False, False, 0)
        box.pack_start(text, True, True, 0)
        dot = self._chip('', 'status-dot', width=6, height=6, valign=Gtk.Align.CENTER)
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

    def on_refresh_list(self, *_):
        hang_breadcrumb('点击刷新实例列表')
        """刷新实例列表：图标转圈 + 底部提示，约 0.7 秒收尾（对齐 Windows 的刷新按钮）。"""
        try:
            self._refresh_stack.set_visible_child_name('spin')
            self._refresh_spin.start()
        except Exception:
            pass
        self._toast('实例列表正在刷新中…')
        try:
            self.refresh()
        except Exception as exc:
            self.append_log('✘ 刷新失败：%s' % exc)
        GLib.timeout_add(700, self._finish_refresh)

    def _finish_refresh(self):
        try:
            self._refresh_spin.stop()
            self._refresh_stack.set_visible_child_name('icon')
        except Exception:
            pass
        try:
            n = len(self.manager.list_instances())
        except Exception:
            n = 0
        self._toast('实例列表已刷新（%d 个）' % n)
        return False

    def on_select(self, *_a):
        """兼容旧调用：把当前选择重新填一遍。"""
        if self.selected is not None:
            self._fill_details(self.selected)

    def _fill_details(self, inst):
        status = inst.status()
        pid = inst.running_pid()
        self.lbl_title.set_text(inst.label)
        self.lbl_crumb.set_text('实例概览')

        ctx = self.chip_badge.get_style_context()
        for cls in ('running', 'needs-repair', 'stopped'):
            ctx.remove_class(cls)
        if status == 'running':
            ctx.add_class('running')
        elif status == 'broken':
            ctx.add_class('needs-repair')
        self.chip_badge.label.set_text(STATUS_TEXT.get(status, status or '—'))

        self.chip_avatar.label.set_text(_initials(inst.label))
        self.lbl_meta_name.set_text(inst.label or 'DeepSeek Harness')
        self.lbl_meta_path.set_text(inst.prefix)
        self.chip_pill_dsh.label.set_text('dsh %s' % (inst.dsh_version or '?'))
        self.chip_pill_node.label.set_text('Node %s' % (inst.node_version or '?'))
        self.lbl_metric_pid.set_text(str(pid) if pid else '—')
        self.lbl_metric_port.set_text(str(inst.port))
        self.lbl_metric_status.set_text(STATUS_TEXT.get(status, status or '—'))
        running = bool(pid)
        self.lbl_live.set_text('服务正常' if running else '未运行')
        # 文字与圆点必须一起换：圆点是独立控件，只改文字会留下一个绿点
        for widget in (self.lbl_live, self.chip_live_dot):
            ctx = widget.get_style_context()
            if running:
                ctx.remove_class('live-stopped')
            else:
                ctx.add_class('live-stopped')

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
            child.sub.set_text(self._row_sub(inst))
        if self.selected is not None:
            fresh = self.manager.instance_at(self.selected.prefix)
            self.selected = fresh
            self._fill_details(fresh)
        return True

    # ------------------------------------------------------------ 日志
    def _push_recent_log(self, text):
        """把一行日志塞进「最近日志」卡（新的在上，最多 15 条，与 Windows 一致）。"""
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
        del self._recent[15:]
        try:
            self.chip_log_count.label.set_text(str(len(self._recent)))
            self.lbl_log_empty.set_visible(not self._recent)
            for idx, (t, lvl, klass, msg) in enumerate(self._recent):
                t_lbl, lvl_chip, msg_lbl, row = self.log_rows[idx]
                t_lbl.set_text(t)
                lvl_chip.label.set_text(lvl)
                lctx = lvl_chip.get_style_context()
                for name in ('success', 'info', 'muted', 'danger'):
                    lctx.remove_class(name)
                lctx.add_class(klass)
                msg_lbl.set_text(msg)
                msg_lbl.set_tooltip_text(msg)
                row.show_all()
            for idx in range(len(self._recent), len(self.log_rows)):
                self.log_rows[idx][3].hide()
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

    # ---- 设置页（设计稿的第二页） ----
    def _build_settings_page(self):
        self.settings_sw = Gtk.ScrolledWindow()
        self.settings_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.get_style_context().add_class('content')
        # 设计稿 .content{padding:25px 30px 15px} —— 用 CSS padding，盒子本身仍是满宽
        self.settings_sw.add(page)

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        heading.set_margin_bottom(22)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        _eyebrow2 = self._label('MANAGER PREFERENCES', 'eyebrow')
        _eyebrow2.set_halign(Gtk.Align.START)
        text.pack_start(_eyebrow2, False, False, 0)
        text.pack_start(self._label('管理器设置', 'page-title'), False, False, 0)
        self.lbl_settings_desc = self._label('查看运行环境，管理外观与维护选项。', 'page-desc')
        text.pack_start(self.lbl_settings_desc, False, False, 0)
        heading.pack_start(text, True, True, 0)
        heading.pack_start(self._button('saveSettings', '✓  保存设置', 'btn', 'btn-primary',
                                        handler=self.on_save_settings), False, False, 0)
        page.pack_start(heading, False, False, 0)

        # 设计稿 .settings-layout：两列 1.5fr/1fr，间距 17（1082 = 639 + 17 + 426）
        grid = Gtk.Grid(column_spacing=17, row_spacing=17)
        grid.get_style_context().add_class('settings-layout')
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)
        left.set_hexpand(True)
        left.set_size_request(639, -1)   # 设计稿左列 639、右列 426
        left.pack_start(self._info_card(), False, False, 0)
        left.pack_start(self._maintenance_card(), False, False, 0)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)
        right.pack_start(self._appearance_card(), False, False, 0)
        right.set_size_request(426, -1)
        grid.attach(left, 0, 0, 1, 1)
        grid.attach(right, 1, 0, 1, 1)
        page.pack_start(grid, False, False, 0)
        return self.settings_sw

    def _settings_card(self, glyph, title, sub):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.get_style_context().add_class('card')
        card.get_style_context().add_class('settings-card')
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        head.pack_start(self._chip(glyph, 'quick-icon', width=34, height=34), False, False, 0)
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
            row.get_style_context().add_class('info-row')
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
        index = theme_index()
        theme, mode = self._theme_state()
        preview.pack_start(self._chip('', 'theme-swatch', 'swatch-%s' % theme,
                                      width=16, height=16, valign=Gtk.Align.CENTER),
                           False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        labels = index.get('labels', {}).get('%s-%s' % (theme, mode), [theme, ''])
        self.lbl_settings_theme = self._label(labels[0], 'quick-title')
        self.lbl_settings_mode = self._label(labels[1], 'quick-sub')
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
            '界面：7 套主题 × 日/夜（令牌从 design/styles.css 抽取生成）',
            '程序目录：%s' % MANAGER_LIB,
            '配置目录：%s' % config_dir(),
            '运行环境：Python %s · GTK %s' % (sys.version.split()[0], gtk_ver),
        ]))

    def on_copy_diag(self, *_):
        self._copy(self._diagnostics_text())
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
        buffer_text = self.log_buf.get_text(self.log_buf.get_start_iter(),
                                            self.log_buf.get_end_iter(), False)
        live = [line for line in buffer_text.splitlines() if line.strip()]
        head = ['—— 管理器日志 ——',
                '文件：%s' % manager_log_path(),
                '本次运行 %d 行；文件最后 %d 行' % (len(live), len(lines)),
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
        self._style_dialog(dlg, '新建实例', '在独立目录里安装一份 DeepSeek Harness（用系统 node/npm）')
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

        def field(label, widget):
            """标签在上、控件在下（对齐 Windows 的表单形态）。"""
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            lbl = Gtk.Label(label=label, xalign=0)
            lbl.get_style_context().add_class('dim-label')
            box.pack_start(lbl, False, False, 0)
            box.pack_start(widget, False, False, 0)
            return box

        grid.attach(field('实例名称', ent_label), 0, 0, 2, 1)
        grid.attach(field('安装目录', box_prefix), 0, 1, 2, 1)
        # 端口与 dsh 版本并排（Windows 版就是这两项一行）
        grid.attach(field('端口', ent_port), 0, 2, 1, 1)
        grid.attach(field('dsh 版本', picker_dsh), 1, 2, 1, 1)
        grid.attach(field('Node 版本', picker_node), 0, 3, 2, 1)
        grid.attach(box_ver, 0, 4, 2, 1)
        hint = Gtk.Label(xalign=0, wrap=True)
        hint.set_text('提示：latest = 最新的非 alpha 版本（由管理器联网解析）；每个实例自带 Node 与 dsh，'
                      '装在所选目录里，数据目录是该目录下的 dsh-home，不会动 ~/.dsh。'
                      '安装需要联网（下载 Node 与 npm 包）。')
        hint.get_style_context().add_class('dim-label')
        grid.attach(hint, 0, 5, 2, 1)
        # 底部条（对齐 Windows）：细线 + 左侧「更新 dsh / Node 版本」+ 右侧 取消/创建实例
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(10)
        grid.attach(sep, 0, 6, 2, 1)
        foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        foot.set_margin_top(12)
        btn_upd = Gtk.Button(label='更新 dsh / Node 版本')
        btn_upd.get_style_context().add_class('foot-btn')
        btn_upd.connect('clicked', lambda *a: fetch_versions())
        foot.pack_start(btn_upd, False, False, 0)
        btn_cancel = Gtk.Button(label='取消')
        btn_cancel.get_style_context().add_class('foot-btn')
        btn_cancel.connect('clicked', lambda *a: dlg.response(Gtk.ResponseType.CANCEL))
        btn_ok = Gtk.Button(label='创建实例')
        btn_ok.get_style_context().add_class('foot-btn')
        btn_ok.get_style_context().add_class('primary')
        btn_ok.connect('clicked', lambda *a: dlg.response(Gtk.ResponseType.OK))
        for b in (btn_upd, btn_cancel, btn_ok):
            b.set_size_request(-1, 32)
        foot.pack_end(btn_ok, False, False, 0)
        foot.pack_end(btn_cancel, False, False, 0)
        grid.attach(foot, 0, 7, 2, 1)
        try:
            area_btn = dlg.get_action_area()
            for child in area_btn.get_children():
                child.hide()
            area_btn.hide()
        except Exception:
            pass
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

        # 端口占用校验：不能被别的实例占着，也不能已被系统监听
        try:
            if port and _port_in_use(port):
                self.append_log('✘ 端口 %d 已被占用（换个端口再试）' % port)
                return
        except Exception:
            pass

        # 目录校验：已存在但「不是本管理器留下的半成品」就拒绝，避免把第二个实例装进别人的目录。
        # 允许 node/ app/ tools/ pnpm-store/ dsh-home/ install.json 这些残留（等于「继续复用」）。
        if os.path.isdir(prefix):
            allowed = {'node', 'app', 'tools', 'pnpm-store', 'dsh-home', 'install.json', 'logs'}
            try:
                foreign = [n for n in os.listdir(prefix) if n not in allowed]
            except Exception:
                foreign = []
            if foreign:
                self.append_log('✘ 目录已存在且不为空（%s），请换一个目录'
                                % ', '.join(foreign[:4]))
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
        self._style_dialog(dlg, title)
        w, h = self._dialog_size(width, height)
        dlg.set_default_size(w, h)
        area = dlg.get_content_area()
        area.set_border_width(14)
        # 表头卡片（对齐 Windows：CardSolid + 1px 内边 + 圆角 10 + padding 12,8）
        thead = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        thead.get_style_context().add_class('plugin-thead')
        thead.set_margin_top(10)
        thead.set_margin_bottom(2)
        thead.set_margin_start(12)
        thead.set_margin_end(12)
        for title, width, expand in (('插件', 190, False), ('仓库 / 说明', 0, True),
                                     ('状态', 110, False), ('版本', 90, False)):
            lbl = Gtk.Label(xalign=0.0, label=title)
            lbl.get_style_context().add_class('plugin-th')
            if expand:
                thead.pack_start(lbl, True, True, 0)
            else:
                lbl.set_size_request(width, -1)
                thead.pack_start(lbl, False, False, 0)
        area.pack_start(thead, False, False, 0)

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
        # 纯查看：非模态 + 自绘关闭（对齐 Windows 的 modeless 日志窗口）
        dlg.connect('response', lambda d, *a: d.destroy())
        dlg.show()

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

    # ------------------------------------------------------------ 对话框统一样式
    def _style_dialog(self, dlg, title, subtitle=''):
        """把 Gtk.Dialog 统一成主界面观感：**没有系统标题栏**（自绘标题区 + 右上关闭），
        并且非模态 —— 对齐 Windows 版：开着插件/日志等子窗口时，管理器与 DSH 窗口都还能用。

        Windows 那边是 WPF 的 Show()（modeless）；GTK 里 modal 是**整个应用**都被锁，
        所以这里必须 set_modal(False)，查看型对话框还要绕开 run()（它自己会临时模态化）。
        """
        dlg.get_style_context().add_class('dsh-dialog')
        # Wayland 下 set_decorated(False) 会被忽略（GTK 退回服务端装饰，KWin 照样画标题栏）。
        # 跟主窗口同一手：decorated=True + 零高度的自绘标题栏 → 协商成 CSD。
        dlg.set_decorated(True)
        _placeholder = Gtk.Box()
        _placeholder.set_size_request(-1, 0)
        dlg.set_titlebar(_placeholder)
        dlg.set_modal(False)          # 不锁住管理器/DSH 窗口
        dlg.set_resizable(True)
        dlg.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)

        area = dlg.get_content_area()
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        head.set_margin_top(16)
        head.set_margin_start(18)
        head.set_margin_end(12)
        head.set_margin_bottom(6)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        lbl = Gtk.Label(xalign=0.0)
        lbl.set_markup('<b>%s</b>' % GLib.markup_escape_text(title))
        lbl.get_style_context().add_class('dialog-title')
        left.pack_start(lbl, False, False, 0)
        if subtitle:
            sub = Gtk.Label(xalign=0.0, wrap=True)
            sub.set_markup(subtitle)
            sub.get_style_context().add_class('dialog-sub')
            left.pack_start(sub, False, False, 0)
        head.pack_start(left, True, True, 0)

        btn_close = Gtk.Button()
        btn_close.set_relief(Gtk.ReliefStyle.NONE)
        btn_close.get_style_context().add_class('icon-btn')
        btn_close.get_style_context().add_class('dlg-close')
        btn_close.set_size_request(28, 28)
        btn_close.set_can_focus(False)        # 不抢焦点 → 没有那圈紫色边框
        btn_close.set_tooltip_text('关闭')
        try:
            btn_close.add(self._icon('x', 'muted', 16))
        except Exception:
            btn_close.set_label('✕')
        btn_close.connect('clicked', lambda *a: dlg.response(Gtk.ResponseType.CLOSE))
        head.pack_end(btn_close, False, False, 0)

        # 按住标题区可以拖窗口（无边框窗口没有系统拖动区）
        head.connect('button-press-event', lambda w, ev: self._drag_window(dlg, w, ev))
        area.pack_start(head, False, False, 0)
        dlg._sub_lbl = sub if subtitle else None

        # 动作区按钮：统一成主界面按钮风格（主操作 accent，其余 secondary）
        try:
            act = dlg.get_action_area()
            kids = act.get_children()
            for idx, btn in enumerate(reversed(kids)):
                btn.get_style_context().add_class('btn')
                btn.get_style_context().add_class('btn-primary' if idx == 0 else 'btn-secondary')
        except Exception:
            pass
        self._dialog_rounded(dlg)
        return dlg

    def _drag_window(self, win, widget, event):
        """无边框窗口：按住标题区拖动（GTK3 的 begin_move_drag）。"""
        try:
            if event.button == 1:
                win.begin_move_drag(event.button, int(event.x_root), int(event.y_root),
                                    event.time)
                return True
        except Exception:
            pass
        return False

    def _dialog_rounded(self, dlg, radius=18):
        """对话框也开 RGBA + 画圆角背景（否则四角是白的方角）。"""
        try:
            screen = Gdk.Screen.get_default()
            visual = screen.get_rgba_visual() if screen is not None else None
            if visual is None or not screen.is_composited() or cairo is None:
                return
            dlg.set_visual(visual)
            dlg.set_app_paintable(True)
            theme, mode = self._theme_state()
            color = Gdk.RGBA()
            color.parse(token_color(theme, mode, 'card-solid'))

            def on_draw(_w, cr):
                alloc = dlg.get_allocation()
                cr.save()
                cr.set_operator(cairo.OPERATOR_SOURCE)
                cr.set_source_rgba(0, 0, 0, 0)
                cr.paint()
                cr.set_operator(cairo.OPERATOR_OVER)
                cr.restore()
                self._rounded_path(cr, 0, 0, alloc.width, alloc.height, radius)
                cr.clip()
                cr.set_source_rgba(color.red, color.green, color.blue, 1.0)
                cr.paint()
                return False

            dlg.connect('draw', on_draw)
            ctx = dlg.get_style_context()
            ctx.add_class('dsh-dialog-flat')
        except Exception:
            pass

    def on_plugins(self, *_):
        inst = self._need()
        if not inst:
            return
        plug.bootstrap_cache()
        where, when = plug.source_info()
        source_text = '来自 %s%s' % (where, (' · 抓取于 %s' % when) if when else '')
        dlg = Gtk.Dialog(title='插件 · %s' % inst.label, transient_for=self, modal=True)
        self._style_dialog(dlg, '插件 · %s' % inst.label,
                           GLib.markup_escape_text(source_text))
        dlg.set_default_size(880, 580)
        area = dlg.get_content_area()
        area.set_border_width(14)
        area.set_spacing(10)

        def refresh_source_label():
            where, when = plug.source_info()
            text = '来自 %s%s' % (where, (' · 抓取于 %s' % when) if when else '')
            lbl = getattr(dlg, '_sub_lbl', None)
            if lbl is not None:
                lbl.set_text(text)

        # 表头 + 行都用同一套列宽自绘（TreeView 的选中是逐 cell 画的，做不到整行一块）
        COLS = ((190, False), (0, True), (110, False), (90, False))
        HEAD = ('插件', '仓库 / 说明', '状态', '版本')

        def make_line(widgets, cls):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            box.get_style_context().add_class(cls)
            for widget, (width, expand) in zip(widgets, COLS):
                cell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                cell.set_size_request(width, -1) if not expand else cell.set_hexpand(True)
                cell.pack_start(widget, expand, expand, 0)
                box.pack_start(cell, expand, expand, 0)
            return box

        head = make_line([self._label(t, 'plugin-th') for t in HEAD], 'plugin-thead')
        head.set_margin_top(10)
        head.set_margin_bottom(4)
        head.set_margin_start(12)   # 与行内左右 12px 的 padding 对齐
        head.set_margin_end(12)
        area.pack_start(head, False, False, 0)

        listbox = Gtk.ListBox()
        listbox.get_style_context().add_class('plugin-list')
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listbox.set_activate_on_single_click(True)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(listbox)
        area.pack_start(sw, True, True, 0)

        # 底部条：一条细线 + 左状态、右操作（对齐 Windows 版）
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(10)
        area.pack_start(sep, False, False, 0)

        foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        foot.set_margin_top(12)
        note = Gtk.Label(xalign=0.0)
        note.set_ellipsize(3)
        note.set_max_width_chars(56)
        note.get_style_context().add_class('foot-note')
        foot.pack_start(note, True, True, 0)

        btn_refresh = Gtk.Button(label='刷新状态')
        btn_install = Gtk.Button(label='安装 / 更新')
        btn_install.get_style_context().add_class('primary')
        btn_uninstall = Gtk.Button(label='卸载')
        btn_uninstall.get_style_context().add_class('danger')
        btn_import = Gtk.Button(label='导入本地包…')
        btn_repo = Gtk.Button(label='打开仓库')
        btn_gh = Gtk.Button(label='刷新 GitHub 列表')
        for btn in (btn_gh, btn_repo, btn_import, btn_uninstall, btn_install, btn_refresh):
            btn.get_style_context().add_class('foot-btn')
            btn.set_size_request(-1, 32)
            foot.pack_end(btn, False, False, 0)
        area.pack_start(foot, False, False, 0)

        state = {'busy': False}

        def current():
            row = listbox.get_selected_row()
            return getattr(row, 'pid', None) if row is not None else None

        def fill(select=None):
          try:
            for child in listbox.get_children():
                listbox.remove(child)
            status = plug.installed(inst)
            theme, mode = self._theme_state()
            first = None
            for item in plug.all_entries(inst):
                st = status.get(item['id'], {})
                if st.get('installed'):
                    label, role = '已安装', 'success'
                elif st.get('package_on_disk') or st.get('registered'):
                    label, role = '半装（需修）', 'danger'
                elif item.get('local_only'):
                    label, role = '未发布', 'muted'
                else:
                    label, role = '未安装', 'muted'
                src = item['repo'] or '（未发布到 GitHub，可本地导入）'
                if item.get('extra'):
                    src = '（实例里已装，不在目录中）'
                extra = ''
                if item.get('updated'):
                    extra = '　★%s · 更新 %s' % (item.get('stars', 0), item['updated'])

                name = self._label(item['id'], 'plugin-id')
                name.set_ellipsize(3)
                repo = self._label('%s — %s%s' % (src, item['desc'], extra), 'plugin-desc')
                repo.set_ellipsize(3)
                st_lbl = self._label(label, 'plugin-status',
                                     {'success': 'ok', 'danger': 'bad'}.get(role, 'dim'))
                ver = self._label(st.get('version') or '—', 'plugin-ver')
                row_box = make_line([name, repo, st_lbl, ver], 'plugin-row-body')
                row = Gtk.ListBoxRow()
                row.get_style_context().add_class('plugin-row')
                row.pid = item['id']
                row.add(row_box)
                listbox.add(row)
                if first is None:
                    first = row
                if select and item['id'] == select:
                    first = row
            target = None
            if select:
                for child in listbox.get_children():
                    if getattr(child, 'pid', None) == select:
                        target = child
                        break
            listbox.select_row(target or first)
            listbox.show_all()
            btn_install.set_sensitive(not state['busy'])
            btn_uninstall.set_sensitive(not state['busy'])
          except Exception:
            import traceback
            traceback.print_exc()

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

        def refresh_github(*_):
            state['busy'] = True
            btn_gh.set_sensitive(False)
            note.set_text('正在从 GitHub 拉取带 dsh-plugin 标签的仓库…')

            def work():
                try:
                    items, fetched = plug.refresh_github()
                    err = ''
                except Exception as exc:
                    items, fetched, err = [], '', str(exc)

                def done():
                    state['busy'] = False
                    btn_gh.set_sensitive(True)
                    refresh_source_label()
                    fill(select=current())
                    if err:
                        note.set_text('拉取失败：%s（列表沿用上次结果）' % err)
                    else:
                        note.set_text('已刷新：GitHub 上 %d 个带 dsh-plugin 标签的仓库' % len(items))
                    return False
                GLib.idle_add(done)

            threading.Thread(target=work, daemon=True).start()

        btn_gh.connect('clicked', refresh_github)

        fill()
        note.set_text('共 %d 个插件' % len(plug.all_entries(inst)))
        # 打开时自动拉一次（不阻塞界面）：没缓存时列表会先用内置目录，拉到后自动刷新
        GLib.timeout_add(200, lambda: (refresh_github(), False)[1])
        dlg.show_all()
        # 非模态：show() 而不是 run()（run 会临时把对话框设成 modal，锁住整个应用）
        dlg.connect('response', lambda d, *a: d.destroy())
        dlg.show()
    # ---- 更新 ----
    def on_update(self, *_):
        inst = self._need()
        if not inst:
            return
        dlg = Gtk.Dialog(title='更新 %s' % inst.label, transient_for=self, modal=True)
        dlg.add_buttons('取消', Gtk.ResponseType.CANCEL, '更新', Gtk.ResponseType.OK)
        self._style_dialog(dlg, '更新 %s' % inst.label)
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

    # ---- 窗口功能 ----
    def on_window_features(self, *_):
        hang_breadcrumb('打开窗口功能')
        """会话窗口里的增强开关（放大平移 / 拖出），与 Windows 的「窗口功能」一致。"""
        dlg, rows = self._build_features_dialog()
        dlg.show_all()
        resp = dlg.run()
        if resp == Gtk.ResponseType.OK:
            self._apply_features(dlg, rows)
        else:
            dlg.destroy()

    def _build_features_dialog(self):
        from dsh_manager import core as _core
        st = _core.load_settings()
        dlg = Gtk.Dialog(title='窗口功能', transient_for=self, modal=True)
        self._style_dialog(dlg, '窗口功能',
                           '这些是管理器给会话窗口额外加的小功能；改完重开窗口生效。')
        dlg.set_default_size(520, 300)
        area = dlg.get_content_area()
        area.set_border_width(14)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        area.pack_start(box, False, False, 0)

        rows = []

        def add_switch(title, desc, key):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.get_style_context().add_class('card')
            card.set_border_width(12)
            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            lbl = Gtk.Label(label=title, xalign=0.0)
            lbl.get_style_context().add_class('danger-title')
            top.pack_start(lbl, True, True, 0)
            sw = Gtk.Switch()
            sw.set_active(bool(st.get(key, True)))
            sw.set_valign(Gtk.Align.CENTER)
            top.pack_end(sw, False, False, 0)
            card.pack_start(top, False, False, 0)
            sub = Gtk.Label(label=desc, xalign=0.0)
            sub.set_line_wrap(True)
            sub.get_style_context().add_class('danger-desc')
            card.pack_start(sub, False, False, 0)
            box.pack_start(card, False, False, 0)
            rows.append((key, sw))

        add_switch('放大后拖动平移', '图片 / PDF 放大超出可视区时，左键拖动可以平移画面。', 'webPan')
        add_switch('文件·目录拖出到系统', '从右侧文件树或会话交付卡把文件/文件夹拖到桌面或资源管理器。',
                   'webDragOut')

        hint = Gtk.Label(xalign=0.0,
                         label='提示：拖出与右键菜单只影响「桌面窗口」；浏览器里打开时仍按网页行为。')
        hint.set_line_wrap(True)
        hint.get_style_context().add_class('foot-note')
        box.pack_start(hint, False, False, 0)

        dlg.add_button('关闭', Gtk.ResponseType.CLOSE)
        ok = dlg.add_button('保存', Gtk.ResponseType.OK)
        ok.get_style_context().add_class('primary')
        return dlg, rows

    def _apply_features(self, dlg, rows):
        from dsh_manager import core as _core
        data = {k: bool(sw.get_active()) for k, sw in rows}
        _core.save_settings(data)
        dlg.destroy()
        self._toast('窗口功能已更新（重开窗口后生效）')

    # ---- 修复 ----
    def on_repair(self, *_):
        inst = self._need()
        if not inst:
            return
        self._run_async('修复 %s' % inst.label, lambda: self.manager.repair(inst.prefix))

    # ---- 删除实例（仪表盘底部的卡）----
    def on_delete_instance(self, *_):
        hang_breadcrumb('点击删除实例')
        inst = self._need()
        if not inst:
            return
        if not self._confirm('删除实例「%s」？' % inst.label,
                             '会先停止服务，然后删除整个目录并从登记表移除，不可恢复：\n%s'
                             % inst.prefix):
            return
        self._toast('正在删除「%s」…' % inst.label)

        def work():
            ok, msg = self.manager.uninstall(inst.prefix)
            GLib.idle_add(lambda: (self._toast(msg), self.refresh(), False)[-1])
            return ok

        self._run_async('删除 %s' % inst.label, work)

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
