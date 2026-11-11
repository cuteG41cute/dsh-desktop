#!/usr/bin/env python3
# 验证「刷新实例列表」的行为：图标切到 spinner、toast 文案变化
import sys
sys.path.insert(0, '/usr/lib/dsh-manager')

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

import dsh_manager.gui as gui

win = gui.ManagerWindow()
win.set_default_size(1220, 900)
win.show_all()

state = {}


def step1():
    print('before: toast=[%s] stack=%s' % (
        win.lbl_toast.get_text() if hasattr(win, 'lbl_toast') else '?',
        win._refresh_stack.get_visible_child_name()))
    win.on_refresh_list()
    print('after click: toast=[%s] stack=%s spinner_active=%s' % (
        win.lbl_toast.get_text(),
        win._refresh_stack.get_visible_child_name(),
        win._refresh_spin.get_visible()))
    return False


def step2():
    print('after 900ms: toast=[%s] stack=%s' % (
        win.lbl_toast.get_text(),
        win._refresh_stack.get_visible_child_name()))
    return False


GLib.timeout_add(600, step1)
GLib.timeout_add(1500, step2)
GLib.timeout_add(2200, Gtk.main_quit)
Gtk.main()
