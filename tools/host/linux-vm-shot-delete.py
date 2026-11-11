#!/usr/bin/env python3
# 构造一个更高的管理器窗口，滚到仪表盘底部并截图（验证「删除实例」卡）
import os
import subprocess
import sys

sys.path.insert(0, '/usr/lib/dsh-manager')

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

import dsh_manager.gui as gui

win = gui.ManagerWindow()
win.set_default_size(1220, 1000)
win.show_all()

state = {}


def find_card():
    found = []

    def walk(w):
        try:
            if 'danger-card' in list(w.get_style_context().list_classes()):
                found.append(w)
                return
        except Exception:
            pass
        try:
            for c in w.get_children():
                walk(c)
        except Exception:
            pass

    walk(win)
    return found[0] if found else None


def after_show():
    card = find_card()
    adj = win.dash_sw.get_vadjustment()
    print('adjustment: upper=%d page=%d value=%d' % (adj.get_upper(), adj.get_page_size(), adj.get_value()))
    adj.set_value(max(0, adj.get_upper() - adj.get_page_size()))
    print('scrolled to %d' % adj.get_value())
    return False


def shoot():
    gdkwin = win.get_window()
    if gdkwin is None:
        print('no gdk window')
        return False
    xid = gdkwin.get_xid()
    print('xid=', xid)
    out = '/tmp/vm-shot-delete.png'
    try:
        subprocess.run(['import', '-window', str(xid), out], check=False, timeout=20)
        print('shot size:', os.path.getsize(out) if os.path.exists(out) else 'missing')
    except Exception as exc:
        print('import failed:', exc)
    return False


GLib.timeout_add(800, after_show)
GLib.timeout_add(1800, shoot)
GLib.timeout_add(3000, Gtk.main_quit)
Gtk.main()
