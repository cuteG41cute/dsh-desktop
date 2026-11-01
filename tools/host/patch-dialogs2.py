"""对话框第二轮：去掉重复标题、关闭按钮放右边、窗口圆角 + 主题背景。

问题（截图 vm-shots/dialog.png）：
1. 标题与说明在自绘标题栏和内容区各出现一次 → 重复；
2. `decoration_layout('close')` 把关闭按钮放到了**左边**（KDE 习惯在右）；
3. 对话框是白底方角，和主窗口的圆角/材质不一致。

修法：
· 内容区不再重复标题（只留一句说明）；
· `decoration_layout(':close')` → 关闭在右；
· 对话框也开 RGBA + 自绘圆角背景（复用主窗口那套：清透明 → 圆角裁切 → 填 card-solid）。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    # 1) 内容区重复标题删掉
    ("        head = Gtk.Label(xalign=0, wrap=True)\n"
     "        head.set_markup('<b>插件 · %s</b>\\n'\n"
     "                        '从我们自己的 GitHub 仓库安装 / 卸载；装在这个实例自己的 profile 里：\\n'\n"
     "                        '<tt>%s</tt>' % (GLib.markup_escape_text(inst.label),\n"
     "                                         GLib.markup_escape_text(plug.profile_dir(inst))))\n"
     "        area.pack_start(head, False, False, 0)",
     "        intro = Gtk.Label(xalign=0, wrap=True)\n"
     "        intro.set_markup('从我们自己的 GitHub 仓库安装 / 卸载；装在这个实例自己的 profile 里。')\n"
     "        intro.get_style_context().add_class('dialog-sub')\n"
     "        area.pack_start(intro, False, False, 0)"),
    # 2) 关闭按钮放右边
    ("        bar.set_decoration_layout('close')",
     "        bar.set_decoration_layout(':close')"),
]

# 对话框也做圆角：在 _style_dialog 里挂 RGBA + 自绘背景
OLD_TAIL = """        except Exception:
            pass
        return dlg
"""
NEW_TAIL = """        except Exception:
            pass
        self._dialog_rounded(dlg)
        return dlg

    def _dialog_rounded(self, dlg, radius=18):
        \"\"\"对话框也开 RGBA + 画圆角背景（否则四角是白的方角）。\"\"\"
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
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    if 'def _dialog_rounded' not in s:
        if OLD_TAIL in s:
            s = s.replace(OLD_TAIL, NEW_TAIL, 1)
        else:
            missing.append('_style_dialog tail')
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0 if not missing else 1


if __name__ == '__main__':
    raise SystemExit(main())
