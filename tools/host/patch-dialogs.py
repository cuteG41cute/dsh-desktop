"""子窗口（对话框）改成与主界面同一套风格，并跟随主题。

现状：Gtk.Dialog 走系统默认外观 —— 白色方角、KDE 标题栏、默认蓝选中、默认按钮。
用户要求：风格与主界面一致 + 随主题变化。

做法：
1. 统一的 `_style_dialog(dlg, title, subtitle)`：
   · 加 `dsh-dialog` 类（主题 CSS 负责背景/圆角/文字色）
   · 换成自绘 CSD 标题栏（HeaderBar + 我们的标题排版 + 关闭按钮）
   · 把动作区按钮统一成 btn / btn-primary 风格
2. 主题 CSS 里补：对话框背景/圆角、HeaderBar 去边框、TreeView/ListBox 的
   文字色与选中色（用 accent-soft，不用系统蓝）、列头、滚动条、dim-label。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

METHOD = '''
    # ------------------------------------------------------------ 对话框统一样式
    def _style_dialog(self, dlg, title, subtitle=''):
        """把 Gtk.Dialog 统一成主界面的观感（自绘标题栏 + 主题按钮 + 主题选中色）。"""
        dlg.get_style_context().add_class('dsh-dialog')
        dlg.set_decorated(True)
        bar = Gtk.HeaderBar()
        bar.get_style_context().add_class('dsh-headerbar')
        bar.set_show_close_button(True)
        bar.set_decoration_layout('close')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl = Gtk.Label(xalign=0.0)
        lbl.set_markup('<b>%s</b>' % GLib.markup_escape_text(title))
        lbl.get_style_context().add_class('dialog-title')
        box.pack_start(lbl, False, False, 0)
        if subtitle:
            sub = Gtk.Label(xalign=0.0)
            sub.set_markup(subtitle)
            sub.get_style_context().add_class('dialog-sub')
            box.pack_start(sub, False, False, 0)
        bar.set_custom_title(box)
        dlg.set_titlebar(bar)
        # 动作区按钮：统一成主界面按钮风格（主操作 accent，其余 secondary）
        try:
            area = dlg.get_action_area()
            kids = area.get_children()
            for idx, btn in enumerate(reversed(kids)):
                btn.get_style_context().add_class('btn')
                btn.get_style_context().add_class('btn-primary' if idx == 0 else 'btn-secondary')
        except Exception:
            pass
        return dlg
'''

CSS_TAIL = """
/* ==========================================================================
 * 子窗口（对话框）：与主界面同一套材质
 * ========================================================================== */
.dsh-dialog {
  background-color: $(card-solid);
  color: $(text);
  border-radius: 18px;
}
.dsh-dialog .dsh-headerbar {
  background-color: transparent;
  background-image: none;
  border: none;
  box-shadow: none;
  padding: 6px 10px;
}
.dsh-dialog .dialog-title { font-size: 13px; font-weight: bold; color: $(text); }
.dsh-dialog .dialog-sub { font-size: 10px; color: $(muted); }
.dsh-dialog .dim-label { color: $(muted); }
.dsh-dialog button { min-height: 30px; }

/* 列表 / 表格：文字与选中色跟主题走（系统默认是蓝底白字） */
.dsh-dialog view,
.dsh-dialog treeview { background-color: transparent; color: $(text); }
.dsh-dialog treeview.view {
  background-color: $(card);
  color: $(text);
  border-radius: 12px;
}
.dsh-dialog treeview.view:hover { background-color: $(hover); }
.dsh-dialog treeview.view:selected,
.dsh-dialog treeview.view:selected:hover {
  background-color: alpha($(accent), .16);
  color: $(text);
}
.dsh-dialog header button,
.dsh-dialog treeview header button {
  background-color: transparent;
  background-image: none;
  border: none;
  box-shadow: none;
  color: $(muted);
  font-size: 10px;
  font-weight: bold;
}
.dsh-dialog list row { background-color: transparent; color: $(text); }
.dsh-dialog list row:hover { background-color: $(hover); }
.dsh-dialog list row:selected { background-color: alpha($(accent), .16); color: $(text); }
.dsh-dialog .panel {
  background-color: transparent;
  border: 1px solid $(inner-border);
  border-radius: 12px;
}
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    if 'def _style_dialog' not in s:
        anchor = '    def on_plugins(self, *_):'
        if anchor not in s:
            raise SystemExit('FAIL: 找不到 on_plugins 锚点')
        s = s.replace(anchor, METHOD + '\n' + anchor, 1)

    # 勾上要改的对话框
    subs = [
        ("        dlg = Gtk.Dialog(title='插件 · %s' % inst.label, transient_for=self, modal=True)\n"
         "        dlg.add_buttons('关闭', Gtk.ResponseType.CLOSE)",
         "        dlg = Gtk.Dialog(title='插件 · %s' % inst.label, transient_for=self, modal=True)\n"
         "        dlg.add_buttons('关闭', Gtk.ResponseType.CLOSE)\n"
         "        self._style_dialog(dlg, '插件 · %s' % inst.label,\n"
         "                           '装在 <tt>%s</tt>'\n"
         "                           % GLib.markup_escape_text(plug.profile_dir(inst)))"),
        ("        dlg = Gtk.Dialog(title=title, transient_for=self, modal=True)\n"
         "        dlg.add_buttons('关闭', Gtk.ResponseType.CLOSE)",
         "        dlg = Gtk.Dialog(title=title, transient_for=self, modal=True)\n"
         "        dlg.add_buttons('关闭', Gtk.ResponseType.CLOSE)\n"
         "        self._style_dialog(dlg, title)"),
        ("        dlg = Gtk.Dialog(title='新建实例', transient_for=self, modal=True)\n"
         "        dlg.add_buttons('取消', Gtk.ResponseType.CANCEL, '安装', Gtk.ResponseType.OK)",
         "        dlg = Gtk.Dialog(title='新建实例', transient_for=self, modal=True)\n"
         "        dlg.add_buttons('取消', Gtk.ResponseType.CANCEL, '安装', Gtk.ResponseType.OK)\n"
         "        self._style_dialog(dlg, '新建实例', '选目录、端口与版本')"),
        ("        dlg = Gtk.Dialog(title='更新 %s' % inst.label, transient_for=self, modal=True)\n"
         "        dlg.add_buttons('取消', Gtk.ResponseType.CANCEL, '更新', Gtk.ResponseType.OK)",
         "        dlg = Gtk.Dialog(title='更新 %s' % inst.label, transient_for=self, modal=True)\n"
         "        dlg.add_buttons('取消', Gtk.ResponseType.CANCEL, '更新', Gtk.ResponseType.OK)\n"
         "        self._style_dialog(dlg, '更新 %s' % inst.label)"),
    ]
    missing = []
    for old, new in subs:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    c = io.open(CSS, encoding='utf-8').read()
    if '子窗口（对话框）' not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('gui patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
