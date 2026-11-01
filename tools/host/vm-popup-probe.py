#!/usr/bin/env python3
"""最小化复现器：验证 WebKitGTK 的 window.open + opener=null + location.replace。

不依赖真人点击：把 enable-javascript-can-open-windows-automatically 打开，
页面就能在定时器里自己 window.open（真实 DSH 是点击手势里同步开的）。

要回答两个问题：
  1. `create` 信号会不会来，我们的"自己开一个 Gtk 窗口 + 返回 WebView"能否成立；
  2. 页面随后 `popup.opener = null; popup.location.replace(url)` 时，
     WebKit 会把返回的那个 WebView 导航走（我们希望），还是直接抛错/关闭弹窗。
"""
import os
import sys

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

URL = os.environ.get('PROBE_URL') or 'http://127.0.0.1:8098/index.html'
ctx = WebKit2.WebContext.get_default()


def log(msg):
    print('[probe] %s' % msg, flush=True)


def tune(view):
    s = view.get_settings()
    for name, value in (('javascript-can-open-windows-automatically', True),
                        ('enable-write-console-messages-to-stdout', True),
                        ('enable-developer-extras', True)):
        try:
            s.set_property(name, value)
        except Exception as exc:
            log('setting %s 失败：%s' % (name, exc))
    view.set_property('settings', s)


class Main(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title='PROBE-MAIN')
        self.set_default_size(900, 620)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.popup = None
        self.web = WebKit2.WebView(web_context=ctx)
        tune(self.web)
        self.web.connect('create', self._on_create)
        self.web.connect('notify::title', lambda v, p: log('主页面 title=%r' % v.get_title()))
        self.add(self.web)
        self.connect('destroy', Gtk.main_quit)

    def _on_create(self, view, action):
        uri = ''
        try:
            req = action.get_request() if action is not None else None
            uri = req.get_uri() if req is not None else ''
        except Exception as exc:
            log('读 create 的请求失败：%s' % exc)
        log('create 信号到达，uri=%r' % uri)
        try:
            win = Gtk.Window(title='PROBE-POPUP')
            win.set_default_size(700, 520)
            win.set_position(Gtk.WindowPosition.CENTER)
            web = WebKit2.WebView(web_context=ctx)
            tune(web)
            web.connect('close', self._on_popup_close)
            web.connect('notify::uri', lambda v, p: log('弹窗 uri=%r' % v.get_uri()))
            web.connect('destroy', lambda *a: log('弹窗 WebView destroy'))
            win.connect('destroy', lambda *a: log('弹窗窗口 destroy'))
            win.add(web)
            win.show_all()
            win.present()
            self.popup = win
            log('已开内置窗口，返回 WebView')
            return web
        except Exception as exc:
            log('开内置窗口失败：%s' % exc)
            return None

    def _on_popup_close(self, view):
        log('弹窗 WebView 收到 close 信号（页面要关它）')
        return True


def main():
    win = Main()
    win.show_all()
    win.web.load_uri(URL)
    log('加载 %s' % URL)

    def report():
        try:
            log('主页面 title=%r' % win.web.get_title())
            log('主页面 uri=%r' % win.web.get_uri())
        except Exception as exc:
            log('report 失败：%s' % exc)
        return False

    GLib.timeout_add(9000, report)
    GLib.timeout_add_seconds(13, lambda: (log('退出'), Gtk.main_quit(), False)[2])
    Gtk.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
