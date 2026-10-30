#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Harness 桌面版 —— Linux 窗口（GTK3 + WebKitGTK）
=========================================================
与 Windows 版（dsh-desktop/App.cs）功能对齐：

  · 预览增强：图片滚轮缩放 / 拖动平移 / 加粗滑动条；PDF Ctrl+滚轮全局缩放；
    右键菜单（保存到… / 复制图片 / 复制文件路径 / 在文件管理器中显示 / 缩放项）；
    「保存到…」弹 **GTK 原生保存对话框，默认「桌面」**，落盘是逐字节复制原文件
  · 拖拽：右栏文件树的行与会话里的交付卡可拖到文件管理器（复制一份）、
    拖进输入框变成待发送附件；文件夹拖进输入框变成路径文字
  · 多会话拖拽分离窗口（拖出侧边栏 → 新窗口显示该会话）、多窗口管理、标题镜像
  · 单实例（再次启动把窗口唤到前台）、托盘、加载进度、window.open、Web 认证 cookie

用法：
  dsh-desktop.py [url]        打开窗口（会按需拉起 dsh web 服务）
  dsh-desktop.py --selftest   不打开窗口，只自检：服务可达性 / cookie 签发 / 注入文件

环境变量：
  DSH_WEB_URL               默认 http://127.0.0.1:3080
  DSH_HOME                  dsh 数据目录（默认 ~/.dsh）
  DSH_DESKTOP_AUTH_COOKIE   预置会话 cookie（name=value）；不设则自己按密钥签发
  DSH_SHARE                 安装后的 share 目录（含 preview-tools.js）
  DSH_DESKTOP_NO_SERVICE=1  不自动拉起服务
  DSH_DRAG_DEBUG_LOG        记录每次「拖出」到的路径（排障用）

依赖：python3, python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1（或 4.0）
"""
import base64
import hashlib
import hmac
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

APP_NAME = 'DeepSeek Harness'
HERE = os.path.dirname(os.path.abspath(__file__))

# 控制台/日志统一 UTF-8：Linux 上本来就是 UTF-8，这里是给「在 Windows 上跑自检」兜底
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DSH_HOME = os.path.expanduser(os.environ.get('DSH_HOME') or '~/.dsh')
WEB_URL = os.environ.get('DSH_WEB_URL') or 'http://127.0.0.1:3080'
if len(sys.argv) > 1 and sys.argv[1] and not sys.argv[1].startswith('-'):
    WEB_URL = sys.argv[1]
AUTH_COOKIE = os.environ.get('DSH_DESKTOP_AUTH_COOKIE', '')
AUTH_MAXAGE = os.environ.get('DSH_DESKTOP_AUTH_COOKIE_MAXAGE', '2592000')
NO_SERVICE = os.environ.get('DSH_DESKTOP_NO_SERVICE') == '1'
UNAUTH_MARKER = 'dsh web authentication required'
SELFTEST = '--selftest' in sys.argv

# 安装后的 share 目录（preview-tools.js 在那儿）；开发目录里则在上两级
SHARE_DIR = os.environ.get('DSH_SHARE') or (
    HERE if os.path.exists(os.path.join(HERE, 'preview-tools.js')) else os.path.dirname(HERE))
PREVIEW_JS = os.path.join(SHARE_DIR, 'preview-tools.js')
ICON_PATH = ''
for cand in (os.path.join(HERE, 'dsh-desktop.png'),
             os.path.join(SHARE_DIR, 'dsh-desktop.png'),
             os.path.join(os.path.dirname(HERE), 'dsh-desktop.png')):
    if os.path.exists(cand):
        ICON_PATH = cand
        break


# ---------------------------------------------------------------------------
# 服务与认证（与 Windows 的 launcher.ps1 同一套：探活 → 拉起 → 签 cookie）
# ---------------------------------------------------------------------------
def _http(url, timeout=3):
    try:
        req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(4096).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            body = e.read(4096).decode('utf-8', 'replace')
        except Exception:
            body = ''
        return e.code, body
    except Exception:
        return 0, ''


def probe_service(url=WEB_URL):
    """'ok' = 已就绪；'auth' = 在跑但需要认证；'down' = 没在跑"""
    code, body = _http(url)
    if code == 200 and '__DSH_BOOT__' in body:
        return 'ok'
    if code == 401 or UNAUTH_MARKER in body:
        return 'auth'
    if code == 200:
        return 'ok'
    return 'down'


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def mint_cookie(home=DSH_HOME, authority=None):
    """按 ~/.dsh/.credentials.yaml 里的 browser-session 密钥签一枚会话 cookie。"""
    if AUTH_COOKIE:
        name, _, value = AUTH_COOKIE.partition('=')
        return name.strip(), value.strip()
    authority = authority or WEB_URL.split('://', 1)[-1].split('/', 1)[0]
    cred = os.path.join(home, '.credentials.yaml')
    if not os.path.exists(cred):
        return None
    try:
        with open(cred, 'r', encoding='utf-8') as fh:
            text = fh.read()
    except Exception:
        return None
    # 与 Windows 启动器 / Linux 启动器同一套取法：client-connection/browser-session 块里的 secret
    import re
    m = re.search(r'client-connection/browser-session:.*?secret:\s*([A-Za-z0-9_\-]+)', text, re.S)
    if not m:
        return None
    secret_raw = m.group(1)
    if not secret_raw:
        return None
    try:
        secret = base64.urlsafe_b64decode(secret_raw + '=' * (-len(secret_raw) % 4))
    except Exception:
        return None
    name = 'dsh-auth-' + _b64url(hashlib.sha256(authority.encode()).digest())
    now = int(time.time() * 1000)
    payload = json.dumps({
        'version': 1,
        'authority': authority,
        'issuedAt': now,
        'expiresAt': now + int(float(AUTH_MAXAGE)) * 1000,
    }, separators=(',', ':')).encode()
    sig = hmac.new(secret, payload, hashlib.sha256).digest()
    return name, 'v1.' + _b64url(payload) + '.' + _b64url(sig)


def find_dsh_entry():
    """在当前安装前缀里找 @deepseek-ai/dsh 的 bin.js（便携安装）。"""
    candidates = []
    for base in (os.environ.get('DSH_PREFIX'), os.path.dirname(SHARE_DIR), HERE,
                 os.path.expanduser('~/.local/opt/deepseek-harness')):
        if not base:
            continue
        candidates.append(os.path.join(base, 'app', 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js'))
    for c in candidates:
        if os.path.exists(c):
            return c
    return ''


def find_node():
    prefix = os.environ.get('DSH_PREFIX') or os.path.dirname(SHARE_DIR)
    for cand in (os.path.join(prefix, 'node', 'bin', 'node'), shutil.which('node')):
        if cand and os.path.exists(cand):
            return cand
    return ''


def start_service():
    """后台拉起 `dsh web --no-open`，日志写到 <prefix>/logs/web.log。"""
    node = find_node()
    entry = find_dsh_entry()
    if not node or not entry:
        return False, '找不到便携 node 或 dsh 入口（请重新运行 install.sh）'
    prefix = os.environ.get('DSH_PREFIX') or os.path.dirname(SHARE_DIR)
    logdir = os.path.join(prefix, 'logs')
    try:
        os.makedirs(logdir, exist_ok=True)
    except Exception:
        pass
    logpath = os.path.join(logdir, 'web.log')
    try:
        port = urllib.parse.urlparse(WEB_URL).port or 3080
    except Exception:
        port = 3080
    env = dict(os.environ)
    env['DSH_HOME'] = DSH_HOME
    args = [node, entry, 'web', '--no-open', '--port', str(port)]
    try:
        log = open(logpath, 'ab', buffering=0)
        subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL, env=env,
                         start_new_session=True)
    except Exception as exc:
        return False, '启动服务失败：%s' % exc
    deadline = time.time() + 90
    while time.time() < deadline:
        st = probe_service()
        if st in ('ok', 'auth'):
            return True, logpath
        time.sleep(1.5)
    return False, '服务在 90 秒内没有就绪，见日志：%s' % logpath


# ---------------------------------------------------------------------------
# 注入脚本
# ---------------------------------------------------------------------------
# 1) 把 Windows 版的 window.chrome.webview 桥接成 WebKit 的消息通道，
#    这样 **同一份** preview-tools.js 在 WebKitGTK 上不用改就能跑。
SHIM_JS = r"""
(function () {
  if (window.chrome && window.chrome.webview) return;
  var handlers = [];
  window.chrome = window.chrome || {};
  window.chrome.webview = {
    postMessage: function (s) {
      try { window.webkit.messageHandlers.dsh.postMessage(String(s)); } catch (e) {}
    },
    addEventListener: function (t, fn) { if (t === 'message' && typeof fn === 'function') handlers.push(fn); }
  };
  // 宿主 -> 页面（GTK 侧用 evaluate_javascript 调它）
  window.__dshHost = function (payload) {
    var obj = payload;
    try { if (typeof payload === 'string') obj = JSON.parse(payload); } catch (e) { return; }
    for (var i = 0; i < handlers.length; i++) { try { handlers[i]({ data: obj }); } catch (e) {} }
  };
})();
"""

# 2) 会话拖拽分离（与 Windows 版同一套手势：拖出侧边栏 -> 开新窗口）
DETACH_JS = r"""
(function () {
  var NEW_SESSION_LABELS = ['新建会话', 'New session'];
  var DRAG_OUT_MARGIN = 24;
  function rowOf(e) { var t = e.target; return t && t.closest ? t.closest('[role="treeitem"]') : null; }
  function rowTitle(row) {
    var best = '', spans = row.querySelectorAll('span');
    for (var i = 0; i < spans.length; i++) {
      var t = (spans[i].textContent || '').trim();
      if (t.length > best.length) best = t;
    }
    return best;
  }
  function send(msg) {
    try { if (window.chrome && window.chrome.webview) window.chrome.webview.postMessage(JSON.stringify(msg)); } catch (e) {}
  }
  document.addEventListener('dragstart', function (e) {
    var row = rowOf(e);
    if (!row) return;
    var id = null;
    try { id = e.dataTransfer.getData('text/plain'); } catch (err) {}
    window.__dshDrag = { id: id, title: rowTitle(row), right: row.getBoundingClientRect().right,
                         selected: row.getAttribute('aria-selected') === 'true' };
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
      if (row) { clearInterval(timer); try { row.click(); } catch (e) {} send({ type: 'dsh-detach-opened', id: id, title: title }); return; }
      if (++tries > 60) clearInterval(timer);
    }, 250);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', openDetached);
  else openDetached();
})();
"""


def load_preview_tools():
    try:
        with open(PREVIEW_JS, 'r', encoding='utf-8') as fh:
            return fh.read()
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# 弹窗 / 外部链接
# ---------------------------------------------------------------------------
def _origin(url):
    try:
        p = urllib.parse.urlsplit(url or '')
        return (p.scheme, p.netloc)
    except Exception:
        return ('', '')


def same_origin(a, b):
    """是不是同一个站点（scheme+host:port）。用于判断弹窗该留在应用内还是交给系统浏览器。"""
    oa = _origin(a)
    return oa == _origin(b) and bool(oa[1])


def open_external(url):
    """把链接交给系统默认浏览器。

    登录页（OAuth/账号登录）必须在真浏览器里完成 —— 它要写自己的 cookie、可能还要
    开新标签继续跳转；放在 WebView 弹窗里做只会把流程搅乱（实测：点了「登录账号」
    后弹窗一闪就关，登录页从没打开过）。
    """
    if not url or not url.lower().startswith(('http://', 'https://')):
        return False
    for cmd in (['xdg-open', url], ['gio', 'open', url]):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return True
        except Exception:
            continue
    sys.stderr.write('[dsh-desktop] 无法打开系统浏览器，请手动访问：%s\n' % url)
    return False


# ---------------------------------------------------------------------------
# 自检（不需要图形界面）
# ---------------------------------------------------------------------------
def selftest():
    ok = True
    print('=== DeepSeek Harness 桌面版（Linux）自检 ===')
    print('DSH_HOME      :', DSH_HOME)
    print('DSH_SHARE     :', SHARE_DIR)
    print('WEB_URL       :', WEB_URL)

    print('\n[1] dsh 数据目录')
    if os.path.isdir(DSH_HOME):
        print('  ✓ 存在')
    else:
        print('  ✗ 不存在（首次运行会由服务创建）')
        ok = False

    print('\n[2] 服务可达性')
    st = probe_service()
    print('  状态:', st)
    if st == 'down' and not NO_SERVICE:
        print('  → 尝试拉起服务…')
        started, detail = start_service()
        print('  %s %s' % ('✓' if started else '✗', detail))
        ok = ok and started
        st = probe_service()

    print('\n[3] 会话 cookie 签发')
    ck = mint_cookie()
    if ck:
        print('  ✓ name=%s  value=%s…（%d 字节）' % (ck[0], ck[1][:18], len(ck[1])))
    else:
        print('  ✗ 没有拿到（.credentials.yaml 里没有 browser-session 密钥？）')
        ok = ok and (st == 'ok')

    print('\n[4] 注入脚本')
    js = load_preview_tools()
    if js:
        marks = ['dsh-save-file', 'dsh-drag-out', 'IS_WEBKIT', 'dsh-read-file']
        missing = [m for m in marks if m not in js]
        print('  ✓ %s（%d 字符）' % (PREVIEW_JS, len(js)))
        if missing:
            print('  ✗ 缺关键片段:', missing)
            ok = False
    else:
        print('  ✗ 找不到 preview-tools.js（期望在 %s）' % PREVIEW_JS)
        ok = False

    print('\n[4b] 弹窗 / 外部链接')
    src = ''
    try:
        with open(os.path.abspath(__file__), 'r', encoding='utf-8') as fh:
            src = fh.read()
    except Exception:
        pass
    popup_marks = (
        ('弹窗按请求的地址打开（不是又开一个应用窗口）', 'req.get_uri()'),
        ('内置浏览器用独立 WebView（不注入 DSH 脚本）', 'WebKit2.WebView(web_context=context)'),
        ('主窗口拒绝页面发起的 window.close()', '_on_view_close'),
        ('窗口可被跨进程唤起（控制套接字）', 'start_control_server'),
        ('无 GPU 时自动软件渲染', 'software_render_if_no_gpu'),
        ('创建 WebView 前真去建一次 GL 上下文', 'probe_gl_context'),
        ('内置浏览器（登录 / 外部页面）', 'class BrowserWindow'),
        ('空白弹窗也返回真实窗口（window.open 不为 null）', 'about:blank'),
    )
    for label, mark in popup_marks:
        if mark in src:
            print('  ✓ ' + label)
        else:
            print('  ✗ %s（缺 %s）' % (label, mark))
            ok = False

    print('\n[5] 便携运行时')
    node = find_node()
    entry = find_dsh_entry()
    print('  node:', node or '（未找到）')
    print('  dsh :', entry or '（未找到）')
    if not node:
        ok = False

    print('\n[6] GTK / WebKitGTK')
    if SELFTEST:
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk  # noqa: F401
            print('  ✓ GTK3 可用')
            try:
                gi.require_version('WebKit2', '4.1')
                print('  ✓ WebKit2 4.1')
            except ValueError:
                gi.require_version('WebKit2', '4.0')
                print('  ✓ WebKit2 4.0')
        except Exception as exc:
            print('  ✗ 缺 GTK/WebKitGTK：%s' % exc)
            print('    安装：sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1')
            ok = False

    print('\n结果:', '全部通过' if ok else '有问题（见上）')
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# 单实例控制套接字（ping / raise / quit）
#   第二个启动器或管理器靠它把已有窗口提到前台，而不是"看到锁就退出"。
# ---------------------------------------------------------------------------
_CONTROL = {'server': None, 'path': None}


def instance_port():
    """这个窗口服务的端口 = 实例标识（多实例时用来区分套接字与锁）。"""
    tag = os.environ.get('DSH_DESKTOP_PORT') or ''
    if tag.isdigit():
        return int(tag)
    try:
        from urllib.parse import urlsplit
        port = urlsplit(WEB_URL).port
        if port:
            return int(port)
    except Exception:
        pass
    return 3080


def control_socket_path():
    """控制套接字：**按实例（端口）分开**。

    以前是「一个用户一个套接字」，开第二个实例的窗口时管理器 ping 到的是第一个
    实例的窗口，于是永远只把第一个窗口提到前台（用户实测：两个实例只显示第一个）。
    路径规则必须与 dsh_manager/core.py 的 Instance.control_socket() 完全一致。
    """
    base = os.environ.get('XDG_RUNTIME_DIR') or '/tmp'
    try:
        uid = os.getuid()
    except Exception:
        uid = 0
    return os.path.join(base, 'dsh-desktop-%d-%d.sock' % (uid, instance_port()))


def nudge_repaint(win, delay=90):
    """让整个窗口重新画一遍（软件渲染下"上半截空白"的兜底）。

    现象：没有 GPU 时（WEBKIT_DISABLE_COMPOSITING_MODE=1）窗口被隐藏/最小化
    再显示回来，WebKit 只重绘它认为脏掉的那一块，剩下一条没画过的灰带。
    改一次窗口尺寸再改回去会让 GTK 作废整个后备存储，是这类问题的通用解法。

    Gdk/GLib 在 run_gui() 里才 import，模块级函数必须自己再导一次（踩过 NameError）。
    """
    from gi.repository import GLib

    def bump():
        try:
            w, h = win.get_size()
            win.resize(w, max(1, h - 1))
        except Exception:
            return False

        def restore():
            try:
                win.resize(w, h)
            except Exception:
                pass
            try:
                gdkwin = win.get_window()
                if gdkwin is not None:
                    gdkwin.invalidate_rect(None, True)
            except Exception:
                pass
            web = getattr(win, 'web', None)
            for obj in (web, win):
                try:
                    if obj is not None:
                        obj.queue_draw()
                except Exception:
                    pass
            return False

        GLib.timeout_add(90, restore)
        return False

    try:
        GLib.timeout_add(delay, bump)
        return True
    except Exception:
        return False


def raise_window(win):
    """把窗口显示出来并提到前台（跨进程唤起时也走这里）。

    Gdk 在 run_gui() 里才 import，模块级函数必须自己再导一次（踩过：NameError）。
    """
    from gi.repository import Gdk
    try:
        if not win.get_visible():
            win.show_all()
        win.deiconify()
    except Exception:
        pass
    for call in ('present_with_time', 'present'):
        try:
            if call == 'present_with_time':
                win.present_with_time(Gdk.CURRENT_TIME)
            else:
                win.present()
            nudge_repaint(win, delay=150)      # 从托盘/最小化回来时补一次整窗重绘
            return True
        except Exception:
            continue
    return False


def start_control_server(win):
    from gi.repository import GLib          # 同上：模块级函数自己导入
    path = control_socket_path()
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass
    family = getattr(socket, 'AF_UNIX', None)
    if family is None:
        sys.stderr.write('[dsh-desktop] 本平台没有 AF_UNIX，跳过控制套接字\n')
        return False
    srv = socket.socket(family, socket.SOCK_STREAM)
    try:
        srv.bind(path)
        os.chmod(path, 0o600)
        srv.listen(8)
        srv.setblocking(False)
    except OSError as exc:
        sys.stderr.write('[dsh-desktop] 控制套接字不可用（%s）：%s\n' % (path, exc))
        try:
            srv.close()
        except Exception:
            pass
        return False

    def on_io(_sock, _cond):
        try:
            conn, _addr = srv.accept()
        except Exception:
            return True
        try:
            conn.settimeout(1.5)
            data = conn.recv(64).decode('utf-8', 'replace').strip()
            if data.startswith('ping'):
                conn.sendall(('ok %d\n' % os.getpid()).encode('utf-8'))
            elif data.startswith('raise'):
                GLib.idle_add(lambda: (raise_window(win), False)[1])
                conn.sendall(b'raised\n')
            elif data.startswith('repaint'):
                GLib.idle_add(lambda: (nudge_repaint(win, delay=0), False)[1])
                conn.sendall(b'repainted\n')
            elif data.startswith('reload'):
                GLib.idle_add(lambda: (win.web.reload(), False)[1])
                conn.sendall(b'reloaded\n')
            elif data.startswith('quit'):
                conn.sendall(b'bye\n')
                GLib.idle_add(lambda: (quit_primary(), False)[1])
            else:
                conn.sendall(b'unknown\n')
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return True

    GLib.io_add_watch(srv, GLib.IO_IN, on_io)
    _CONTROL['server'] = srv
    _CONTROL['path'] = path
    return True


def stop_control_server():
    srv = _CONTROL.get('server')
    if srv is not None:
        try:
            srv.close()
        except Exception:
            pass
    path = _CONTROL.get('path')
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass
    _CONTROL['server'] = None
    _CONTROL['path'] = None


def quit_primary():
    from gi.repository import Gtk           # 同上
    for w in list(_WINDOWS):
        try:
            w.destroy()
        except Exception:
            pass
    Gtk.main_quit()


# 供控制套接字使用：主窗口列表（run_gui 里填）
_WINDOWS = []


def software_render_if_no_gpu():
    """虚拟机里没有 /dev/dri 时强制软件渲染。

    Hyper-V 等环境 WebKit 拿不到 EGL 上下文（日志里 EGL/MESA/ZINK 那堆报错），
    窗口进程活着但界面出不来——实测就是这个现象。
    """
    if os.environ.get('DSH_DESKTOP_GL') == 'on':
        return
    if os.environ.get('WEBKIT_DISABLE_COMPOSITING_MODE') == '1':
        return
    if not os.path.isdir('/dev/dri'):
        os.environ['WEBKIT_DISABLE_COMPOSITING_MODE'] = '1'
        os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')


def probe_gl_context():
    """真去建一次 GL 上下文，用来判断这台机器的 GL 栈到底能不能用。

    为什么不能只看 /dev/dri：KVM / Hyper-V 的虚拟机里 /dev/dri 往往是 virtio_gpu，
    设备节点在、Mesa 却选不到 pdev（日志：
      libEGL warning: failed to get driver name for fd -1
      MESA: error: ZINK: failed to choose pdev
      libEGL warning: egl: failed to create dri2 screen
    ）—— 那种机器必须走软件渲染，否则窗口只画出一部分（实测：上半截一块灰板）。

    WebKit 的 EGL 和 GDK 的 EGL 是同一套 Mesa/EGL，所以这个探测能预先发现它。
    **必须在创建 WebView 之前调用**：软件渲染靠环境变量，WebKit 只在初始化时读一次。

    返回 None 表示能用 GPU；返回字符串表示问题描述。
    """
    if os.environ.get('DSH_DESKTOP_GL') == 'on':
        return None                     # 用户强制走 GPU，就别拦
    from gi.repository import Gtk       # 模块级函数自己导入（踩过 NameError）
    holder = None
    try:
        holder = Gtk.OffscreenWindow()
        holder.set_default_size(2, 2)
        holder.show_all()
        gdkwin = holder.get_window()
        if gdkwin is None:
            holder.destroy()
            holder = Gtk.Window()
            holder.set_default_size(2, 2)
            holder.realize()
            gdkwin = holder.get_window()
        if gdkwin is None:
            return 'GDK 窗口没有底层 surface'
        if not hasattr(gdkwin, 'create_gl_context'):
            return None                 # 老 GTK 没有这个 API，无从判断
        ctx = gdkwin.create_gl_context()
        if ctx is None:
            return 'GDK 没能创建 GL 上下文'
        if hasattr(ctx, 'make_current'):
            try:
                if not ctx.make_current():
                    return 'GL 上下文无法设为当前'
            except Exception as exc:
                return 'GL 上下文不可用：%s' % exc
        return None
    except Exception as exc:
        return 'GL 上下文探测失败：%s' % exc
    finally:
        try:
            if holder is not None:
                holder.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 图形界面
# ---------------------------------------------------------------------------
def run_gui():
    import gi
    gi.require_version('Gtk', '3.0')
    for ver in ('4.1', '4.0'):
        try:
            gi.require_version('WebKit2', ver)
            break
        except ValueError:
            continue
    from gi.repository import Gtk, Gdk, GLib, Gio, WebKit2

    # 创建 WebView 之前先确认 GL 真的能用：不可用就强制软件渲染。
    # 这一步必须在这里做（而不是只靠启动器看 /dev/dri），否则 WebKit 已经按 GPU
    # 初始化了，再设环境变量也没用。
    gl_problem = probe_gl_context()
    if gl_problem:
        os.environ['WEBKIT_DISABLE_COMPOSITING_MODE'] = '1'
        os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
        sys.stderr.write('[dsh-desktop] %s → 已强制软件渲染\n' % gl_problem)
    else:
        sys.stderr.write('[dsh-desktop] GL 探测通过，使用 GPU 渲染\n')

    # 共享的内存态 WebContext：不碰系统密钥环（Deepin 上会弹「解锁登录密钥环」），多窗口共享会话
    context = WebKit2.WebContext.new_ephemeral()
    windows = _WINDOWS          # 与 quit_primary() 共用同一个列表

    class App:
        def __init__(self):
            self.primary = None
            self.tray = None

    app = App()

    # ---------------- WebView ----------------
    class DshWebView(WebKit2.WebView):
        def __init__(self, url, window, inject=True):
            WebKit2.WebView.__init__(self, web_context=context)
            self.window = window
            ucm = self.get_user_content_manager()
            ucm.connect('script-message-received::dsh', self._on_message)
            ucm.register_script_message_handler('dsh')
            self._scripts = []          # 注入的脚本在 _install_scripts() 里统一加

            settings = self.get_settings()
            for name, value in (('enable-developer-extras', True),
                                ('enable-write-console-messages-to-stdout', True),
                                ('hardware-acceleration-policy', None),
                                ('enable-smooth-scrolling', True)):
                if value is None:
                    continue
                try:
                    settings.set_property(name, value)
                except Exception:
                    pass
            # 允许把文件拖进页面（文件→附件走产品自己的 drop 处理）
            try:
                self.set_property('settings', settings)
            except Exception:
                pass
            # inject=False 用于站外弹窗（登录页等第三方页面）：不注入 DSH 的注入脚本，
            # 免得预览增强/拖拽/分离那些逻辑去改人家的页面
            if inject:
                self._install_scripts()
            self.connect('load-changed', self._on_load_changed)
            self.connect('create', self._on_create)
            self.load_uri(url)

        def _install_scripts(self):
            ucm = self.get_user_content_manager()
            js = load_preview_tools()
            if js:
                # 预览增强（与 Windows 同一份文件）：只对「桌面窗口」注入
                ucm.add_script(WebKit2.UserScript(
                    js, WebKit2.UserContentInjectedFrames.TOP_FRAME,
                    WebKit2.UserScriptInjectionTime.START, None, None))
            ucm.add_script(WebKit2.UserScript(
                SHIM_JS, WebKit2.UserContentInjectedFrames.TOP_FRAME,
                WebKit2.UserScriptInjectionTime.START, None, None))
            ucm.add_script(WebKit2.UserScript(
                DETACH_JS, WebKit2.UserContentInjectedFrames.TOP_FRAME,
                WebKit2.UserScriptInjectionTime.START, None, None))

        def run_js(self, script, callback=None):
            try:
                self.evaluate_javascript(script, -1, None, None, None, callback, None)
                return True
            except Exception:
                pass
            try:
                self.run_javascript(script, None, callback, None)
                return True
            except Exception:
                return False

        def reply(self, obj):
            payload = json.dumps(obj, ensure_ascii=False)
            self.run_js('window.__dshHost && window.__dshHost(%s)' % payload)

        def _on_message(self, ucm, result):
            try:
                js = result.get_js_value()
                text = js.to_string() if hasattr(js, 'to_string') else str(js)
                msg = json.loads(text)
            except Exception:
                return
            try:
                self.window.handle_message(self, msg)
            except Exception as exc:
                print('[dsh] 消息处理失败:', exc, file=sys.stderr)

        # ---- 认证 ----
        def _on_load_changed(self, view, event):
            if event != WebKit2.LoadEvent.FINISHED:
                return
            window = self.window
            window.set_progress(0)
            if window.auth_done or not AUTH_COOKIE and not window.cookie:
                return
            value = '%s; path=/; max-age=%s; SameSite=Strict' % (window.cookie_value, AUTH_MAXAGE)
            script = (
                "(function () { try {"
                "  var text = document.body ? (document.body.innerText || '') : '';"
                "  if (text.indexOf(%s) < 0) return 'skip';"
                "  document.cookie = %s;"
                "  location.reload(); return 'injected';"
                "} catch (e) { return 'error'; } })()"
                % (json.dumps(UNAUTH_MARKER), json.dumps(value)))
            self.run_js(script)

        def _on_create(self, view, action):
            """页面要开新窗口时（window.open / target=_blank）。

            关键点：**必须返回一个真实的 WebView**，否则 WebKit 视作"弹窗被拦"，
            `window.open()` 返回 null —— DSH 的登录就靠它弹授权页，一旦返回 null
            就只会显示「没有自动打开新页面？复制登录链接…」的兜底提示（实测就是这样）。

            因此这里分成三条：
              - `about:blank` / 空地址：照样开一个**内置浏览器**空窗口并返回它，
                页面随后会把地址写进去（OAuth 流程常见：先 open('') 再给 location 赋值）；
              - 站内地址：开应用窗口（保留会话分离体验）；
              - 站外地址（登录页、外部站点）：开**内置浏览器**窗口，不注入 DSH 脚本。
            非 http(s) 协议（mailto: 等）仍交给系统处理。
            """
            uri = ''
            try:
                req = action.get_request() if action is not None else None
                uri = req.get_uri() if req is not None else ''
            except Exception:
                uri = ''
            uri = (uri or '').strip()
            low = uri.lower()

            if uri and not low.startswith(('http://', 'https://', 'about:blank', 'data:')):
                # mailto: / 自定义协议 之类，交给系统处理
                sys.stderr.write('[dsh-desktop] 新窗口请求交给系统（%s）\n' % uri)
                open_external(uri)
                return None

            try:
                if uri and same_origin(uri, WEB_URL):
                    win = DshWindow(uri, primary=False)
                else:
                    win = BrowserWindow(uri or 'about:blank', parent=self.window)
                win.show_all()
                win.present()
                sys.stderr.write('[dsh-desktop] 新窗口已开：%s\n' % (uri or '(空白页)'))
                return win.web
            except Exception as exc:
                sys.stderr.write('[dsh-desktop] 开新窗口失败（%s）：%s\n' % (uri, exc))
                return None

    # ---------------- 窗口 ----------------
    class DshWindow(Gtk.Window):
        def __init__(self, url, primary=False, inject=True):
            Gtk.Window.__init__(self, title=APP_NAME)
            self.url = url
            self.primary = primary
            self.inject = inject
            self.auth_done = False
            self.set_default_size(1440, 900)
            self.set_position(Gtk.WindowPosition.CENTER)
            if ICON_PATH:
                try:
                    self.set_icon_from_file(ICON_PATH)
                except Exception:
                    pass
            ck = mint_cookie()
            self.cookie = bool(ck)
            self.cookie_value = ('%s=%s' % (ck[0], ck[1])) if ck else ''

            overlay = Gtk.Overlay()
            self.web = DshWebView(url, self, inject)
            overlay.add(self.web)
            self.spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.spinner_box.set_valign(Gtk.Align.CENTER)
            self.spinner_box.set_halign(Gtk.Align.CENTER)
            self.progress = Gtk.ProgressBar()
            self.progress.set_size_request(220, 6)
            self.progress.set_show_text(False)
            self.spinner_box.add(self.progress)
            self.spinner_box.set_no_show_all(True)
            overlay.add_overlay(self.spinner_box)
            self.add(overlay)
            self.web.connect('notify::title', self._on_title)
            self.web.connect('load-changed', self._on_load)
            self.connect('destroy', self._on_destroy)
            self.connect('delete-event', self._on_delete)
            windows.append(self)
            if primary:
                app.primary = self
                # 页面脚本里的 window.close() 不能把主窗口关掉：登录/登出流程在弹窗里
                # 关闭自己是可以的，但顶层窗口被关就等于"应用自己退出了"（实测踩过）。
                try:
                    self.web.connect('close', self._on_view_close)
                except Exception:
                    pass

        def _on_view_close(self, *_args):
            """WebKitWebView::close —— 返回 True 表示"我处理了，别关"。"""
            return True

        def set_progress(self, value):
            if value <= 0:
                self.spinner_box.hide()
            else:
                self.spinner_box.show_all()
                self.progress.set_fraction(value)

        def _on_load(self, view, event):
            if event == WebKit2.LoadEvent.STARTED:
                self.set_progress(0.15)
                GLib.timeout_add(120, self._pulse)
            elif event in (WebKit2.LoadEvent.FINISHED, WebKit2.LoadEvent.REDIRECTED):
                self.set_progress(0)

        def _pulse(self):
            if not self.spinner_box.get_visible():
                return False
            self.progress.pulse()
            return True

        def _on_title(self, view, pspec):
            title = view.get_title()
            if title:
                self.set_title(title)

        def _on_delete(self, widget, event):
            # 与 Windows 版一致：主窗口的 X = 收进托盘（没有托盘就直接关）
            if self.primary and app.tray is not None:
                self.hide()
                return True
            return False

        def _on_destroy(self, widget):
            if self in windows:
                windows.remove(self)
            if not windows:
                Gtk.main_quit()

        # ---- 宿主消息 ----
        def handle_message(self, web, msg):
            mtype = msg.get('type')
            if mtype == 'dsh-detach':
                from urllib.parse import quote
                sid = msg.get('id', '')
                title = msg.get('title', '')
                if sid:
                    base = web.window.url.split('?')[0] if hasattr(web, 'window') else self.url
                    w = DshWindow('%s?detach=%s&title=%s' % (base, quote(sid), quote(title)))
                    w.show_all()
                return
            if mtype == 'dsh-save-file':
                self._save_file(web, msg)
                return
            if mtype == 'dsh-copy-image':
                self._copy_image(web, msg)
                return
            if mtype == 'dsh-reveal':
                self._reveal(msg)
                return
            if mtype == 'dsh-read-file':
                self._read_file(web, msg)
                return
            if mtype == 'dsh-drag-out':
                # Linux 上拖出由页面原生 HTML5 拖拽负责（见 preview-tools.js 的 IS_WEBKIT 分支），
                # 这里只记录一下，便于排障
                log = os.environ.get('DSH_DRAG_DEBUG_LOG')
                if log:
                    try:
                        with open(log, 'a', encoding='utf-8') as fh:
                            fh.write('%s\t%s\n' % (time.strftime('%H:%M:%S'), self._dec(msg, 'pathB64')))
                    except Exception:
                        pass
                return

        # ---- 消息工具 ----
        @staticmethod
        def _dec(msg, key):
            raw = msg.get(key)
            if not raw:
                return ''
            try:
                return base64.b64decode(raw).decode('utf-8')
            except Exception:
                return ''

        @staticmethod
        def _enc(text):
            return base64.b64encode((text or '').encode('utf-8')).decode('ascii')

        def _reply(self, web, obj):
            web.reply(obj)

        # ---- 保存（GTK 原生对话框，默认桌面） ----
        def _save_file(self, web, msg):
            req = msg.get('requestId', '')
            src = self._dec(msg, 'pathB64')
            name = self._dec(msg, 'nameB64') or os.path.basename(src) or 'file'
            data = msg.get('data')
            if not src and not data:
                self._reply(web, {'type': 'dsh-save-file-result', 'requestId': req, 'ok': False,
                                  'reason': 'error', 'messageB64': self._enc('没有源文件')})
                return
            dialog = Gtk.FileChooserDialog(title='保存文件', parent=self, action=Gtk.FileChooserAction.SAVE)
            dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '保存', Gtk.ResponseType.OK)
            dialog.set_do_overwrite_confirmation(True)
            dialog.set_current_name(name)
            desktop = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)
            if desktop:
                try:
                    dialog.set_current_folder(desktop)      # 默认目录 = 桌面
                except Exception:
                    pass
            ext = os.path.splitext(name)[1].lower().lstrip('.')
            if ext:
                flt = Gtk.FileFilter()
                flt.set_name('当前格式 (*.%s)' % ext)
                flt.add_pattern('*.%s' % ext)
                dialog.add_filter(flt)
            allf = Gtk.FileFilter()
            allf.set_name('所有文件')
            allf.add_pattern('*')
            dialog.add_filter(allf)
            try:
                resp = dialog.run()
            finally:
                target = dialog.get_filename()
                dialog.destroy()
            if resp != Gtk.ResponseType.OK or not target:
                self._reply(web, {'type': 'dsh-save-file-result', 'requestId': req, 'ok': False, 'reason': 'cancelled'})
                return
            try:
                if src and os.path.exists(src):
                    shutil.copyfile(src, target)            # 逐字节复制原文件
                else:
                    raw = base64.b64decode(data)
                    with open(target, 'wb') as fh:
                        fh.write(raw)
            except Exception as exc:
                self._reply(web, {'type': 'dsh-save-file-result', 'requestId': req, 'ok': False,
                                  'reason': 'error', 'messageB64': self._enc(str(exc))})
                return
            self._reply(web, {'type': 'dsh-save-file-result', 'requestId': req, 'ok': True,
                              'pathB64': self._enc(target)})

        # ---- 复制图片（位图 + 文件 URI） ----
        def _copy_image(self, web, msg):
            req = msg.get('requestId', '')
            src = self._dec(msg, 'pathB64')
            ok = False
            try:
                clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
                uri = Gio.File.new_for_path(src).get_uri()
                targets = Gtk.TargetList.new([])
                targets.add_image_targets(0, True)          # image/png 等
                targets.add_uri_targets(1)                  # text/uri-list（粘到文件管理器 = 复制文件）

                def _get(clip, selection, info, user_data):
                    if info == 1:
                        selection.set_uris([uri])
                        return
                    try:
                        from gi.repository import GdkPixbuf
                        pix = GdkPixbuf.Pixbuf.new_from_file(src)
                        selection.set_pixbuf(pix)
                    except Exception:
                        pass

                clipboard.set_with_data(targets, _get, lambda *a: None, None)
                clipboard.store()
                ok = True
            except Exception:
                ok = False
            self._reply(web, {'type': 'dsh-copy-image-result', 'requestId': req, 'ok': ok})

        # ---- 在文件管理器中显示 ----
        def _reveal(self, msg):
            src = self._dec(msg, 'pathB64')
            if not src or not os.path.exists(src):
                return
            uri = Gio.File.new_for_path(src).get_uri()
            try:
                proc = subprocess.Popen(
                    ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.FileManager1',
                     '--object-path', '/org/freedesktop/FileManager1',
                     '--method', 'org.freedesktop.FileManager1.ShowItems',
                     "['%s']" % uri, '""'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
            try:
                subprocess.Popen(['xdg-open', os.path.dirname(src)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        # ---- 读文件（WebKit 上「页面自己拖的文件只有 URI」，需要宿主把字节给它） ----
        def _read_file(self, web, msg):
            src = self._dec(msg, 'pathB64')
            req = msg.get('requestId', '')
            try:
                if not src or not os.path.isfile(src):
                    raise FileNotFoundError(src or '(空路径)')
                if os.path.getsize(src) > 64 * 1024 * 1024:
                    raise ValueError('文件超过 64MB')
                with open(src, 'rb') as fh:
                    raw = fh.read()
                self._reply(web, {'type': 'dsh-read-file-result', 'ok': True,
                                  'dataB64': base64.b64encode(raw).decode('ascii'),
                                  'nameB64': self._enc(os.path.basename(src))})
            except Exception as exc:
                self._reply(web, {'type': 'dsh-read-file-result', 'ok': False,
                                  'message': str(exc)})

    # ---------------- 内置浏览器（给"需要弹出一个网页"的工况） ----------------
    class BrowserWindow(Gtk.Window):
        """内置浏览器窗口：登录页、外部链接、OAuth 授权页都走它。

        与主窗口的区别：**不注入 DSH 的任何脚本、不签认证 cookie**，
        只带一个极简工具栏（返回 / 刷新 / 用系统浏览器打开）和当前地址。

        之所以要"内置"而不是丢给系统浏览器：登录流程往往依赖 `window.open()`
        返回的那个窗口对象（`opener`、`w.closed`、`postMessage`），交给系统浏览器
        这条链就断了；而返回 null 会让 DSH 直接显示「没有自动打开新页面」。
        """

        def __init__(self, uri, parent=None):
            Gtk.Window.__init__(self, title='DeepSeek Harness · 内置浏览器')
            self.uri = uri or 'about:blank'
            self.set_default_size(1000, 780)
            self.set_position(Gtk.WindowPosition.CENTER)
            if ICON_PATH:
                try:
                    self.set_icon_from_file(ICON_PATH)
                except Exception:
                    pass

            hb = Gtk.HeaderBar()
            hb.set_show_close_button(True)
            hb.props.title = '内置浏览器'
            hb.props.subtitle = '登录 / 外部页面'
            btn_back = Gtk.Button.new_from_icon_name('go-previous-symbolic', Gtk.IconSize.BUTTON)
            btn_back.set_tooltip_text('后退')
            btn_back.connect('clicked', lambda *a: _safe(self.web.go_back))
            btn_reload = Gtk.Button.new_from_icon_name('view-refresh-symbolic', Gtk.IconSize.BUTTON)
            btn_reload.set_tooltip_text('刷新')
            btn_reload.connect('clicked', lambda *a: _safe(self.web.reload))
            btn_ext = Gtk.Button.new_from_icon_name('web-browser-symbolic', Gtk.IconSize.BUTTON)
            btn_ext.set_tooltip_text('改用系统浏览器打开这个地址')
            btn_ext.connect('clicked', lambda *a: open_external(self.web.get_uri() or self.uri))
            hb.pack_start(btn_back)
            hb.pack_start(btn_reload)
            hb.pack_end(btn_ext)
            self.set_titlebar(hb)

            self.web = WebKit2.WebView(web_context=context)
            try:
                settings = self.web.get_settings()
                settings.set_property('enable-developer-extras', True)
                self.web.set_property('settings', settings)
            except Exception:
                pass

            self.lbl_url = Gtk.Label(xalign=0)
            self.lbl_url.set_ellipsize(3)          # END
            self.lbl_url.set_margin_top(3)
            self.lbl_url.set_margin_bottom(3)
            self.lbl_url.set_margin_start(8)
            self.lbl_url.set_margin_end(8)
            self.lbl_url.get_style_context().add_class('dim-label')
            self.lbl_url.set_text(self.uri)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            box.pack_start(self.lbl_url, False, False, 0)
            box.pack_start(self.web, True, True, 0)
            self.add(box)

            self.web.connect('notify::uri', self._on_uri)
            self.web.connect('notify::title', self._on_title)
            self.web.connect('load-changed', self._on_load)
            self.connect('destroy', self._on_destroy)
            _WINDOWS.append(self)
            _safe(lambda: self.web.load_uri(self.uri))

        def _on_uri(self, view, _pspec=None):
            self.lbl_url.set_text(view.get_uri() or '')

        def _on_title(self, view, _pspec=None):
            title = view.get_title() or view.get_uri() or ''
            self.set_title(('%s · 内置浏览器' % title)[:80] if title else '内置浏览器')

        def _on_load(self, view, event):
            if event == WebKit2.LoadEvent.FINISHED:
                self._on_uri(view)
                self._on_title(view)

        def _on_destroy(self, _w):
            if self in _WINDOWS:
                _WINDOWS.remove(self)

    def _safe(fn, *args):
        """调用可能失败的 WebKit 操作（历史为空时 go_back 会报错）。"""
        try:
            return fn(*args)
        except Exception:
            return None

    # ---------------- 单实例 / 托盘 / 主循环 ----------------
    def make_tray(show_window, quit_app):
        try:
            icon = Gtk.StatusIcon()
            icon.set_tooltip_text(APP_NAME)
            if ICON_PATH:
                icon.set_from_file(ICON_PATH)
            else:
                icon.set_from_icon_name('applications-internet')
            icon.connect('activate', lambda *a: show_window())
            menu = Gtk.Menu()
            item_show = Gtk.MenuItem(label='显示窗口')
            item_show.connect('activate', lambda *a: show_window())
            item_quit = Gtk.MenuItem(label='退出')
            item_quit.connect('activate', lambda *a: quit_app())
            menu.append(item_show)
            menu.append(item_quit)
            menu.show_all()
            icon.connect('popup-menu', lambda i, b, t: menu.popup(None, None, Gtk.StatusIcon.position_menu, i, b, t))
            icon.set_visible(True)
            app.tray = icon
            return icon
        except Exception:
            app.tray = None
            return None

    def show_primary():
        if app.primary is not None:
            raise_window(app.primary)

    def quit_app():
        for w in list(windows):
            try:
                w.destroy()
            except Exception:
                pass
        Gtk.main_quit()

    primary = DshWindow(WEB_URL, primary=True)
    primary.show_all()
    make_tray(show_primary, quit_app)
    start_control_server(primary)   # 让启动器/管理器能 ping 和 raise 这个窗口
    Gtk.main()
    stop_control_server()
    return 0


def main():
    if SELFTEST or '--check' in sys.argv:
        return selftest()
    # 必须在初始化 GTK / 创建 WebView 之前：虚拟机无 /dev/dri 时切软件渲染
    software_render_if_no_gpu()
    if not NO_SERVICE or probe_service() == 'down':
        st = probe_service()
        if st == 'down':
            started, detail = start_service()
            print('[dsh] 服务:', '已启动' if started else detail, file=sys.stderr)
    return run_gui()


if __name__ == '__main__':
    sys.exit(main())
