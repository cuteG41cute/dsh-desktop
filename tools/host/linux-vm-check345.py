#!/usr/bin/env python3
# Verify: (3) install failure cleanup, (4) 15 log rows, (5) UI watchdog writes hang.log
import os
import shutil
import sys
import time

sys.path.insert(0, '/usr/lib/dsh-manager')

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

import dsh_manager.core as core
import dsh_manager.gui as gui

print('=== (3) install failure cleanup ===')
prefix = '/tmp/dsh-install-fail-test'
shutil.rmtree(prefix, ignore_errors=True)
m = core.Manager()
m._install_node = lambda inst, v: None


def boom(inst, v):
    raise RuntimeError('boom: simulated npm failure')


m._npm_install = boom
ok, msg, inst = m.install(prefix, '9.9.9', '9.9.9', 3987, 'failtest')
print('ok=%s msg=%s' % (ok, msg[:60]))
print('dir_exists_after_failure=%s (want False)' % os.path.exists(prefix))

print('=== (4) log card rows ===')
win = gui.ManagerWindow()
win.set_default_size(1220, 900)
win.show_all()
print('log_rows=%d (want 15)' % len(win.log_rows))
for i in range(20):
    win.append_log('test log line %d' % i)
time.sleep(0.6)
while Gtk.events_pending():
    Gtk.main_iteration_do(False)
print('recent_kept=%d (want 15)' % len(win._recent))
print('visible_rows=%d' % sum(1 for r in win.log_rows if r[3].get_visible()))

print('=== (5) watchdog ===')
hang = os.path.join(os.path.dirname(core.settings_path()), 'hang.log')
try:
    os.remove(hang)
except OSError:
    pass
print('hang_log_before=%s' % os.path.exists(hang))
GLib.timeout_add(300, lambda: (time.sleep(12), False)[1])
GLib.timeout_add(14000, Gtk.main_quit)
Gtk.main()
try:
    text = open(hang, encoding='utf-8').read()
    print('hang_log_after=True lines=%d' % len(text.strip().splitlines()))
    print('--- hang.log ---')
    print(text.strip()[:400])
except OSError as exc:
    print('hang_log_after=missing (%s)' % exc)
