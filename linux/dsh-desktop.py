#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Harness 桌面版 - Linux 窗口（WebKitGTK）
与 Windows 版功能对齐：多会话拖拽分离窗口、多窗口管理、标题镜像、窗口内导航。

用法：dsh-desktop.py [url]
  默认地址 http://127.0.0.1:3080（可用环境变量 DSH_WEB_URL 覆盖）

依赖：python3-gi, gir1.2-webkit2-4.1（或 4.0）, gir1.2-gtk-3.0
"""
import json
import os
import sys

import gi

gi.require_version('Gtk', '3.0')
try:
    gi.require_version('WebKit2', '4.1')
except ValueError:
    gi.require_version('WebKit2', '4.0')
from gi.repository import Gtk, GLib, WebKit2

BASE_URL = os.environ.get('DSH_WEB_URL', 'http://127.0.0.1:3080')
if len(sys.argv) > 1 and sys.argv[1]:
    BASE_URL = sys.argv[1]

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dsh-desktop.png')

# 共享的内存态 WebContext（ephemeral）：
# - 不访问系统密钥环（避免 Deepin「解锁登录密钥环」弹窗）
# - 多窗口（拖拽分离）共享同一 session/cookie
_SHARED_CONTEXT = WebKit2.WebContext.new_ephemeral()

# ---------------------------------------------------------------------------
# 注入脚本（与 Windows 版同一套逻辑；通信通道为 WebKit 的
# window.webkit.messageHandlers.dsh）：拖出侧边栏 -> 通知宿主开新窗口；
# 新窗口读取 ?detach= 参数 -> 按标题匹配会话并点击打开。
# ---------------------------------------------------------------------------
INJECT_SCRIPT = r"""
(function () {
  var NEW_SESSION_LABELS = ['新建会话', 'New session'];
  var DRAG_OUT_MARGIN = 24;

  function rowOf(e) { var t = e.target; return t && t.closest ? t.closest('[role="treeitem"]') : null; }
  function rowTitle(row) {
    var best = '';
    var spans = row.querySelectorAll('span');
    for (var i = 0; i < spans.length; i++) {
      var t = (spans[i].textContent || '').trim();
      if (t.length > best.length) best = t;
    }
    return best;
  }
  function send(msg) {
    try {
      if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.dsh) {
        window.webkit.messageHandlers.dsh.postMessage(JSON.stringify(msg));
      }
    } catch (e) {}
  }

  document.addEventListener('dragstart', function (e) {
    var row = rowOf(e);
    if (!row) return;
    var id = null;
    try { id = e.dataTransfer.getData('text/plain'); } catch (err) {}
    window.__dshDrag = {
      id: id,
      title: rowTitle(row),
      right: row.getBoundingClientRect().right,
      selected: row.getAttribute('aria-selected') === 'true'
    };
  }, true);

  document.addEventListener('dragend', function (e) {
    var drag = window.__dshDrag;
    window.__dshDrag = null;
    if (!drag) return;
    if (e.clientX <= drag.right + DRAG_OUT_MARGIN) return;
    send({ type: 'dsh-detach', id: encodeURIComponent(drag.id), title: encodeURIComponent(drag.title), selected: drag.selected });
    if (drag.selected) {
      var btn = null;
      for (var i = 0; i < NEW_SESSION_LABELS.length && !btn; i++) {
        btn = document.querySelector('button[aria-label="' + NEW_SESSION_LABELS[i] + '"]');
      }
      if (btn) btn.click();
    }
  }, true);

  function openDetached() {
    var params = new URLSearchParams(window.location.search);
    var id = params.get('detach');
    var title = params.get('title') || '';
    if (!id) return;
    try { history.replaceState(null, '', window.location.pathname + window.location.hash); } catch (e) {}
    var tries = 0;
    var timer = setInterval(function () {
      var row = null;
      if (title) {
        var rows = document.querySelectorAll('[role="treeitem"]');
        for (var i = 0; i < rows.length && !row; i++) {
          var spans = rows[i].querySelectorAll('span');
          for (var j = 0; j < spans.length; j++) {
            if ((spans[j].textContent || '').trim() === title) { row = rows[i]; break; }
          }
        }
      }
      if (row) {
        clearInterval(timer);
        try { row.click(); } catch (e) {}
        send({ type: 'dsh-detach-opened', id: id, title: title });
        return;
      }
      if (++tries > 60) clearInterval(timer);
    }, 250);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', openDetached);
  } else {
    openDetached();
  }
})();
"""


class DshWebView(WebKit2.WebView):
    """带注入脚本与宿主消息通道的 WebView。
    使用共享的内存态（ephemeral）WebContext：不访问系统密钥环，
    避免 Deepin 弹出「解锁登录密钥环」；多窗口共享同一 session。"""

    def __init__(self, url, owner):
        super().__init__(web_context=_SHARED_CONTEXT)
        self.owner = owner
        ucm = self.get_user_content_manager()
        ucm.add_script(WebKit2.UserScript(
            INJECT_SCRIPT,
            WebKit2.UserContentInjectedFrames.ALL_FRAMES,
            WebKit2.UserScriptInjectionTime.START,
            [], []))
        ucm.connect('script-message-received::dsh', self._on_message)
        ucm.register_script_message_handler('dsh')
        self.get_settings().set_property('enable-developer-extras', True)
        self.load_uri(url)

    def _on_message(self, ucm, result):
        try:
            js = result.get_js_value()
            text = js.to_string() if hasattr(js, 'to_string') else str(js)
            msg = json.loads(text)
        except Exception:
            return
        mtype = msg.get('type')
        if mtype == 'dsh-detach':
            sid = msg.get('id', '')
            title = msg.get('title', '')
            if sid:
                base = self.owner.url.split('?')[0]
                from urllib.parse import quote
                detach_url = '%s?detach=%s&title=%s' % (base, quote(sid), quote(title))
                self.owner.open_detached_window(detach_url)
        # 'dsh-detach-opened' 仅作确认，无需处理


class DshWindow(Gtk.Window):
    """桌面窗口：主窗口关闭即退出；子窗口（分离窗口）关闭仅关自身。"""

    def __init__(self, url, is_primary=False):
        Gtk.Window.__init__(self, title='DeepSeek Harness')
        self.url = url
        self.is_primary = is_primary
        self.set_default_size(1440, 900)
        self.set_position(Gtk.WindowPosition.CENTER)
        if os.path.exists(ICON_PATH):
            try:
                self.set_icon_from_file(ICON_PATH)
            except Exception:
                pass

        self.web = DshWebView(url, self)
        self.web.connect('notify::title', self._on_title)
        self.web.connect('create', self._on_create)
        self.add(self.web)
        self.connect('destroy', self._on_destroy)

    def _on_title(self, webview, pspec):
        title = webview.get_title()
        if title:
            self.set_title(title)

    def _on_create(self, webview, action):
        """window.open（如页面触发）-> 新窗口。"""
        new_win = DshWindow(BASE_URL, is_primary=False)
        new_win.show_all()
        return new_win.web

    def _on_destroy(self, widget):
        # 主窗口关闭 = 退出程序（服务由启动器停止）；
        # 子窗口（分离窗口）关闭仅关自身；最后一个窗口关闭也退出。
        windows = [w for w in Gtk.window_list() if isinstance(w, DshWindow)]
        if self.is_primary or len(windows) <= 1:
            Gtk.main_quit()

    def open_detached_window(self, url):
        win = DshWindow(url, is_primary=False)
        win.show_all()


def main():
    win = DshWindow(BASE_URL, is_primary=True)
    win.show_all()
    Gtk.main()


if __name__ == '__main__':
    main()
