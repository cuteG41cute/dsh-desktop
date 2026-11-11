#!/usr/bin/env python3
# 在真实 X11 会话里构造一次管理器窗口，检查「删除实例」卡与侧栏刷新按钮是否存在
import os
import sys

sys.path.insert(0, '/usr/lib/dsh-manager')

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import dsh_manager.gui as gui

win = gui.ManagerWindow()
win.set_default_size(1220, 900)
win.show_all()

found = {'danger-card': None, 'refresh-btn': None, 'toast': None}


def walk(widget, depth=0):
    try:
        ctx = widget.get_style_context()
        classes = list(ctx.list_classes())
    except Exception:
        classes = []
    if 'danger-card' in classes and found['danger-card'] is None:
        found['danger-card'] = widget
    if isinstance(widget, Gtk.Button) and getattr(win, 'btn_refresh_side', None) is widget:
        found['refresh-btn'] = widget
    if getattr(win, 'toast_revealer', None) is widget:
        found['toast'] = widget
    try:
        children = widget.get_children()
    except Exception:
        children = []
    for child in children:
        walk(child, depth + 1)


walk(win)

print('danger_card:', 'yes' if found['danger-card'] is not None else 'NO')
print('refresh_btn:', 'yes' if found['refresh-btn'] is not None else 'NO')
print('has_on_refresh_list:', hasattr(win, 'on_refresh_list'))
print('has_on_delete_instance:', hasattr(win, 'on_delete_instance'))

# 让「删除实例」的按钮文案可读
if found['danger-card'] is not None:
    labels = []

    def collect(w):
        try:
            if isinstance(w, Gtk.Label):
                labels.append(w.get_text())
        except Exception:
            pass
        for c in (w.get_children() if hasattr(w, 'get_children') else []):
            collect(c)

    collect(found['danger-card'])
    print('danger_card_labels:', ' | '.join([x for x in labels if x]))
    alloc = found['danger-card'].get_allocation()
    print('danger_card_alloc:', alloc.width, 'x', alloc.height)

# 侧栏按钮 tooltip
if found['refresh-btn'] is not None:
    print('refresh_btn_tip:', found['refresh-btn'].get_tooltip_text())

Gtk.main_quit()
