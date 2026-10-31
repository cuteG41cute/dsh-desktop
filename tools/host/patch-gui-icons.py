"""Patch 6: 把设计稿的 SVG 图标接进 GTK（替换原来的 Unicode 字形）。

- 新增 icon_pixbuf()：按颜色替换 currentColor 后交给 GdkPixbuf 的 svg loader；
- 新增 token_color()：从 themes.json 取主题色，图标颜色随主题/日夜变；
- ManagerWindow._icon() 返回 Gtk.Image，并登记到 self._icons，apply_theme 时重上色；
- _button(icon=…) / _chip(icon=…) 改走图标，字形表兜底。
"""
import io

P = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

HELPERS = '''

# ---------------------------------------------------------------- 图标
# 设计稿的 27 个图标是 <symbol id="i-*"> 里的 24×24 描边路径，
# tools/extract-icons.mjs 已经把每个抽成 dsh_manager/icons/<name>.svg，
# 运行时只要把 currentColor 换成主题色，再让 GdkPixbuf 的 svg loader 画出来。
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
_ICON_CACHE = {}

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
        sys.stderr.write('[dsh-manager] 图标 %s 渲染失败：%s\\n' % (name, exc))
        pb = None
    if pb is not None and (pb.get_width() != px or pb.get_height() != px):
        pb = pb.scale_simple(px, px, GdkPixbuf.InterpType.HIGH_QUALITY)
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
'''

SUBS = [
    # 1) 导入 GdkPixbuf + json
    ("from gi.repository import Gdk, Gio, GLib, Gtk, Pango",
     "from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango"),
    # 2) 在 CSS_FILE 之后插入图标helper
    ("CSS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'style.css')",
     "CSS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'style.css')" + HELPERS),
    # 3) _chip 支持 icon= 参数（图标块，如快捷功能区的 34×34）
    ("        lbl = Gtk.Label(label=text, xalign=0.5, yalign=0.5)\n"
     "        box.add(lbl)\n"
     "        box.label = lbl",
     "        if kwargs.get('icon'):\n"
     "            img = self._icon(kwargs['icon'], kwargs.get('role', 'accent'),\n"
     "                             kwargs.get('icon_size', 17))\n"
     "            box.add(img)\n"
     "            lbl = Gtk.Label(label='')\n"
     "            lbl.set_visible(False)\n"
     "            box.pack_start(lbl, False, False, 0)\n"
     "        else:\n"
     "            img = None\n"
     "            lbl = Gtk.Label(label=text, xalign=0.5, yalign=0.5)\n"
     "            box.add(lbl)\n"
     "        box.image = img\n"
     "        box.label = lbl"),
    # 4) _button 的 icon= 改走图标
    ("        if kwargs.get('icon'):\n"
     "            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)\n"
     "            box.pack_start(Gtk.Label(label=kwargs['icon']), False, False, 0)\n"
     "            box.pack_start(Gtk.Label(label=label), False, False, 0)\n"
     "            btn.add(box)",
     "        if kwargs.get('icon'):\n"
     "            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)\n"
     "            role = kwargs.get('icon_role') or ('on-accent' if 'btn-primary' in classes\n"
     "                                               else 'muted')\n"
     "            widget = self._icon_for(kwargs['icon'], role, kwargs.get('icon_size', 16))\n"
     "            if widget is not None:\n"
     "                box.pack_start(widget, False, False, 0)\n"
     "            else:\n"
     "                box.pack_start(Gtk.Label(label=kwargs['icon']), False, False, 0)\n"
     "            box.pack_start(Gtk.Label(label=label), False, False, 0)\n"
     "            btn.add(box)"),
]

METHODS = '''
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
'''


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:70])
            continue
        s = s.replace(old, new, 1)

    # 图标名清单（供 _icon_for 判断）
    if '_ICON_NAMES = ' not in s:
        s = s.replace("_ICON_CACHE = {}\n",
                      "_ICON_CACHE = {}\n_ICON_NAMES = set()\ntry:\n"
                      "    _ICON_NAMES = {f[:-4] for f in os.listdir(ICON_DIR) if f.endswith('.svg')}\n"
                      "except OSError:\n    pass\n", 1)

    # 方法：插到 _chip 定义之前
    if 'def _icon_for(self' not in s:
        anchor = "    def _chip(self, text='', *classes, **kwargs):"
        if anchor in s:
            s = s.replace(anchor, METHODS + '\n' + anchor, 1)
        else:
            missing.append('anchor _chip')

    # 初始化 self._icons，并在 apply_theme 后重上色
    if 'self._icons = []' not in s:
        s = s.replace("        self._theme_buttons = {}\n",
                      "        self._theme_buttons = {}\n        self._icons = []\n", 1)
    if 'self._recolor_icons()' not in s:
        s = s.replace("        self._sync_theme_labels(theme, mode)\n        return ok",
                      "        self._sync_theme_labels(theme, mode)\n"
                      "        try:\n"
                      "            self._recolor_icons()\n"
                      "        except Exception:\n"
                      "            pass\n        return ok", 1)

    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched %d/%d; missing: %s' % (len(SUBS) - len(missing), len(SUBS),
                                         missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
