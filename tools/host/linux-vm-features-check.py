#!/usr/bin/env python3
# 验证「窗口功能」对话框：构建 → 截图 → 切换 webPan → 保存 → 读 settings.json
import json
import os
import subprocess
import sys

sys.path.insert(0, '/usr/lib/dsh-manager')

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

import dsh_manager.gui as gui
import dsh_manager.core as core

win = gui.ManagerWindow()
win.set_default_size(1220, 900)
win.show_all()

dlg, rows = win._build_features_dialog()
dlg.show_all()

state = {'rows': rows, 'dlg': dlg}


def shoot(tag):
    try:
        xid = dlg.get_window().get_xid() if dlg.get_window() else None
        if xid:
            subprocess.run(['import', '-window', str(xid), '/tmp/shot-features-%s.png' % tag],
                           check=False, timeout=20)
            print('shot %s ok' % tag)
        else:
            print('shot %s: no gdk window' % tag)
    except Exception as exc:
        print('shot %s failed: %s' % (tag, exc))


def step1():
    print('rows:', [(k, sw.get_active()) for k, sw in state['rows']])
    shoot('before')
    for k, sw in state['rows']:
        if k == 'webPan':
            sw.set_active(False)
    return False


def step2():
    win._apply_features(dlg, state['rows'])
    try:
        with open(core.settings_path(), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        print('settings:', json.dumps({k: data.get(k) for k in ('webPan', 'webDragOut')}, ensure_ascii=False))
    except Exception as exc:
        print('settings read failed:', exc)
    print('toast:', win.lbl_toast.get_text() if hasattr(win, 'lbl_toast') else '?')
    return False


GLib.timeout_add(700, step1)
GLib.timeout_add(1700, step2)
GLib.timeout_add(2400, Gtk.main_quit)
Gtk.main()
