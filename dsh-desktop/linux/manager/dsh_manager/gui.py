# -*- coding: utf-8 -*-
"""dsh-manager 图形界面（GTK3）。

一次装好、长期用：在同一个窗口里管多个 DSH 实例 ——
每个实例有自己的安装目录、Node、dsh 版本、数据目录和端口，互不干扰。
"""
import os
import threading

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

from .core import (DEFAULT_DSH, DEFAULT_NODE, MANAGER_VERSION, Manager,  # noqa: E402
                   port_free)

STATUS_TEXT = {
    'running': '运行中',
    'starting': '启动中',
    'external': '端口有服务（非本管理器）',
    'stopped': '已停止',
    'broken': '不完整（需修复）',
}


class ManagerWindow(Gtk.Window):
    def __init__(self, manager=None):
        Gtk.Window.__init__(self, title='DeepSeek Harness 管理器 %s' % MANAGER_VERSION)
        self.manager = manager or Manager()
        self.set_default_size(1000, 680)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.selected = None
        self.busy = False
        self._build()
        self.refresh()
        GLib.timeout_add(400, self._drain_log)
        GLib.timeout_add(4000, self._tick)

    # ------------------------------------------------------------ 界面
    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)

        # 顶栏
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.props.title = 'DeepSeek Harness 管理器'
        hb.props.subtitle = '多实例 · 多版本 · 安装 / 更新 / 修复 / 卸载'
        btn_new = Gtk.Button(label='＋ 新建实例')
        btn_new.get_style_context().add_class('suggested-action')
        btn_new.connect('clicked', self.on_new)
        hb.pack_start(btn_new)
        btn_refresh = Gtk.Button.new_from_icon_name('view-refresh-symbolic', Gtk.IconSize.BUTTON)
        btn_refresh.set_tooltip_text('刷新')
        btn_refresh.connect('clicked', lambda *a: self.refresh())
        hb.pack_end(btn_refresh)
        self.set_titlebar(hb)

        # 中部：左列表 + 右详情
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(560)
        root.pack_start(paned, True, True, 0)

        # 左：实例列表
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_border_width(8)
        self.store = Gtk.ListStore(str, str, str, str, str, str)   # label, prefix, dsh, node, port, status
        self.tree = Gtk.TreeView(model=self.store)
        for i, (title, width) in enumerate((('名称', 150), ('dsh', 92), ('node', 80),
                                            ('端口', 56), ('状态', 120))):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i + (0 if i == 0 else 1))
            col.set_resizable(True)
            col.set_min_width(width)
            self.tree.append_column(col)
        self.tree.connect('cursor-changed', self.on_select)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.tree)
        left.pack_start(scroll, True, True, 0)
        self.lbl_prefix = Gtk.Label(label='', xalign=0)
        self.lbl_prefix.set_ellipsize(3)      # END
        self.lbl_prefix.get_style_context().add_class('dim-label')
        left.pack_start(self.lbl_prefix, False, False, 0)
        paned.pack1(left, True, False)

        # 右：详情 + 操作
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_border_width(10)
        self.lbl_title = Gtk.Label(label='选择左侧的实例', xalign=0)
        self.lbl_title.get_style_context().add_class('title-2')
        right.pack_start(self.lbl_title, False, False, 0)
        self.lbl_info = Gtk.Label(label='', xalign=0, wrap=True)
        right.pack_start(self.lbl_info, False, False, 0)

        grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        self.buttons = {}
        for idx, (key, label) in enumerate((('start', '启动服务'), ('stop', '停止服务'),
                                            ('open', '打开窗口'), ('update', '更新版本'),
                                            ('repair', '修复'), ('uninstall', '卸载'),
                                            ('folder', '在文件管理器中显示'))):
            btn = Gtk.Button(label=label)
            btn.connect('clicked', getattr(self, 'on_' + key))
            grid.attach(btn, idx % 3, idx // 3, 1, 1)
            self.buttons[key] = btn
        right.pack_start(grid, False, False, 4)

        # 日志
        logs = Gtk.Frame(label='日志')
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_buf = self.log_view.get_buffer()
        sw.add(self.log_view)
        logs.add(sw)
        right.pack_start(logs, True, True, 0)
        paned.pack2(right, True, False)
        self.set_buttons_sensitive(False)

    def set_buttons_sensitive(self, has_selection):
        for key, btn in self.buttons.items():
            btn.set_sensitive(has_selection and not self.busy)
        if self.selected is not None:
            self.buttons['start'].set_sensitive(not self.busy and self.selected.status() == 'stopped')
            self.buttons['stop'].set_sensitive(not self.busy and bool(self.selected.running_pid()))

    def append_log(self, line):
        end = self.log_buf.get_end_iter()
        self.log_buf.insert(end, line.rstrip('\n') + '\n')
        mark = self.log_buf.create_mark(None, self.log_buf.get_end_iter(), False)
        self.log_view.scroll_mark_onscreen(mark)

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
                    row[5] = STATUS_TEXT.get(inst.status(), inst.status())
        if self.selected is not None:
            self._fill_details(self.selected)
        return True

    # ------------------------------------------------------------ 列表/详情
    def refresh(self):
        self.store.clear()
        instances = self.manager.list_instances()
        for inst in instances:
            self.store.append([inst.label, inst.prefix, inst.dsh_version or '-',
                               inst.node_version or '-', str(inst.port),
                               STATUS_TEXT.get(inst.status(), inst.status())])
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
        self.lbl_title.set_text(inst.label)
        self.lbl_info.set_text(
            '安装位置：%s\n'
            'dsh %s · Node %s · 端口 %d\n'
            '数据目录：%s\n'
            '状态：%s' % (inst.prefix, inst.dsh_version or '?', inst.node_version or '?',
                        inst.port, inst.dsh_home, STATUS_TEXT.get(inst.status(), inst.status())))

    # ------------------------------------------------------------ 动作（线程里跑）
    def _run_async(self, title, fn, on_done=None):
        if self.busy:
            return
        self.busy = True
        self.set_buttons_sensitive(True)
        self.append_log('—— %s ——' % title)
        self.set_title('DeepSeek Harness 管理器 · %s…' % title)

        def worker():
            try:
                result = fn()
            except Exception as exc:          # 兜底：任何异常都别把界面卡死
                result = (False, '异常：%s' % exc, None)
            GLib.idle_add(self._finish, title, result, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, title, result, on_done):
        self.busy = False
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

        combo_dsh = Gtk.ComboBoxText()
        for v in self.manager.available_dsh_versions(8):
            combo_dsh.append_text(v)
        combo_dsh.set_active(0)
        combo_node = Gtk.ComboBoxText()
        for v in self.manager.available_node_versions():
            combo_node.append_text(v)
        combo_node.set_active(0)
        if not combo_node.get_active_text():
            combo_node.append_text(DEFAULT_NODE)
            combo_node.set_active(0)

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
                ('dsh 版本', combo_dsh), ('Node 版本', combo_node)]
        for r, (label, widget) in enumerate(rows):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, r, 1, 1)
            grid.attach(widget, 1, r, 1, 1)
        hint = Gtk.Label(xalign=0, wrap=True)
        hint.set_text('提示：每个实例自带 Node 与 dsh，装在所选目录里；数据目录是该目录下的 dsh-home，'
                      '不会动 ~/.dsh。安装需要联网（下载 Node 与 npm 包）。')
        hint.get_style_context().add_class('dim-label')
        grid.attach(hint, 0, len(rows), 2, 1)
        dlg.show_all()
        resp = dlg.run()
        if resp != Gtk.ResponseType.OK:
            dlg.destroy()
            return
        prefix = ent_prefix.get_text().strip()
        label = ent_label.get_text().strip() or os.path.basename(prefix)
        port = int(ent_port.get_value())
        dsh = combo_dsh.get_active_text() or DEFAULT_DSH
        node = combo_node.get_active_text() or DEFAULT_NODE
        dlg.destroy()
        if os.path.exists(prefix) and not os.path.isdir(prefix):
            self.append_log('✘ 目标路径已存在且不是目录：%s' % prefix)
            return
        self._run_async('安装 %s' % os.path.basename(prefix),
                        lambda: self.manager.install(prefix, dsh, node, port, label))

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
            return inst.open_window()
        self._run_async('打开窗口 %s' % inst.label, job)

    def on_folder(self, *_):
        inst = self._need()
        if not inst:
            return
        import subprocess
        try:
            subprocess.Popen(['xdg-open', inst.prefix])
        except Exception as exc:
            self.append_log('✘ 打开目录失败：%s' % exc)

    # ---- 更新 ----
    def on_update(self, *_):
        inst = self._need()
        if not inst:
            return
        dlg = Gtk.Dialog(title='更新 %s' % inst.label, transient_for=self, modal=True)
        dlg.add_buttons('取消', Gtk.ResponseType.CANCEL, '更新', Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=8, row_spacing=10, border_width=12)
        dlg.get_content_area().add(grid)

        combo_dsh = Gtk.ComboBoxText.new_with_entry()
        vers = self.manager.available_dsh_versions(10)
        for v in vers:
            combo_dsh.append_text(v)
        combo_dsh.get_child().set_text(inst.dsh_version or (vers[0] if vers else DEFAULT_DSH))
        combo_node = Gtk.ComboBoxText.new_with_entry()
        for v in self.manager.available_node_versions():
            combo_node.append_text(v)
        combo_node.get_child().set_text(inst.node_version or DEFAULT_NODE)

        grid.attach(Gtk.Label(label='dsh 版本', xalign=0), 0, 0, 1, 1)
        grid.attach(combo_dsh, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label='Node 版本', xalign=0), 0, 1, 1, 1)
        grid.attach(combo_node, 1, 1, 1, 1)
        note = Gtk.Label(xalign=0, wrap=True)
        note.set_text('更新只动这个实例的目录；正在跑的话先停服务再更新（服务会自动另起）。')
        note.get_style_context().add_class('dim-label')
        grid.attach(note, 0, 2, 2, 1)
        dlg.show_all()
        if dlg.run() != Gtk.ResponseType.OK:
            dlg.destroy()
            return
        dsh = combo_dsh.get_child().get_text().strip() or inst.dsh_version
        node = combo_node.get_child().get_text().strip() or inst.node_version
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


def run_gui():
    win = ManagerWindow()
    win.connect('destroy', Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0
