# -*- coding: utf-8 -*-
"""dsh-manager 核心：多实例（多开）、多版本安装 / 更新 / 修复 / 卸载 / 启停。

设计要点
--------
* **便携**：每个实例是一个目录（prefix），里面自带 node + dsh + dsh-home，
  互不干扰；管理器不往系统里装任何 Node/dsh。
* **可脚本化**：这个模块不 import gi，`dsh-manager --headless <cmd>` 可直接用，
  也方便自动化测试。
* **实例发现**：既读取管理器的注册表（~/.config/dsh-manager/instances.json），
  也会扫描几个常见根目录里带 install.json 的前缀（例如用 install.sh 装过的）。
"""
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

APP = 'dsh-manager'
NPM_PKG = '@deepseek-ai/dsh'
DEFAULT_NODE = '24.19.0'
DEFAULT_DSH = '0.1.5-rc.1'
DEFAULT_ROOT = os.path.expanduser('~/.local/opt')
FALLBACK_DSH_VERSIONS = ['0.1.5-rc.1']
FALLBACK_NODE_VERSIONS = ['24.19.0', '22.11.0', '20.19.0']
SYSTEM_SHARE = '/usr/lib/dsh-manager/share'      # deb 里随包带的窗口文件
MANAGER_VERSION = '1.1.6'
MANAGER_LIB = '/usr/lib/dsh-manager'             # 管理器自己的安装目录（deb）


# --------------------------------------------------------------------------- 管理器自身的配置与日志
def config_dir():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, APP)


def settings_path():
    return os.path.join(config_dir(), 'settings.json')


def manager_log_path():
    return os.path.join(config_dir(), 'manager.log')


DEFAULT_SETTINGS = {
    'theme': True,          # 企业简洁风主题（关掉 = GTK 默认皮肤）
    'logLines': 800,        # 日志面板保留行数
}


def load_settings():
    data = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), 'r', encoding='utf-8') as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            data.update({k: v for k, v in loaded.items() if k in DEFAULT_SETTINGS})
    except Exception:
        pass
    return data


def save_settings(data):
    merged = load_settings()
    merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
    try:
        os.makedirs(config_dir(), exist_ok=True)
        tmp = settings_path() + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(merged, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, settings_path())
        return True
    except Exception:
        return False


def append_manager_log(line):
    """把日志面板里的一行也落盘，方便事后排障（>512KB 轮转一次）。"""
    path = manager_log_path()
    try:
        os.makedirs(config_dir(), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            try:
                os.replace(path, path + '.1')
            except Exception:
                pass
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(line.rstrip('\n') + '\n')
    except Exception:
        pass


def read_manager_log(limit=200):
    path = manager_log_path()
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            lines = fh.readlines()
    except Exception:
        return []
    return [ln.rstrip('\n') for ln in lines[-limit:]]


# --------------------------------------------------------------------------- 工具
def _b64(text):
    return base64.b64encode((text or '').encode('utf-8')).decode('ascii')


def now_iso():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def eprint(*args):
    print(*args, file=sys.stderr)


def port_free(port, host='127.0.0.1'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) != 0


def probe(url, timeout=3):
    """返回 (code, body)。code=0 表示连不上。"""
    try:
        req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(2048).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            body = e.read(2048).decode('utf-8', 'replace')
        except Exception:
            body = ''
        return e.code, body
    except Exception:
        return 0, ''


def _semver_key(version):
    """排序键：先比主次修订号，正式版 > 预发布版，预发布里再按数字逐段比（rc.10 > rc.9）。"""
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)', version or '')
    nums = [int(x) for x in m.groups()] if m else [0, 0, 0]
    pre = version[len(m.group(0)):] if m else ''
    return nums + [0 if pre else 1] + [int(x) for x in re.findall(r'\d+', pre)]


def arch_tag():
    m = os.uname().machine if hasattr(os, 'uname') else 'x86_64'
    return 'linux-arm64' if m in ('aarch64', 'arm64') else 'linux-x64'


# --------------------------------------------------------------------------- 实例
class Instance:
    """一个安装前缀 = 一个实例（独立 node / dsh / 数据目录 / 端口）。"""

    def __init__(self, prefix, meta=None):
        self.prefix = os.path.abspath(os.path.expanduser(prefix))
        self.meta = meta or {}
        self.label = self.meta.get('label') or os.path.basename(self.prefix)
        self.port = int(self.meta.get('port') or 3080)
        self.dsh_version = self.meta.get('dsh') or ''
        self.node_version = self.meta.get('node') or ''
        self.dsh_home = self.meta.get('dshHome') or os.path.join(self.prefix, 'dsh-home')
        self.pidfile = os.path.join(self.prefix, 'logs', 'web.pid')
        self.logfile = os.path.join(self.prefix, 'logs', 'web.log')

    # ---- 路径 ----
    @property
    def node(self):
        return os.path.join(self.prefix, 'node', 'bin', 'node')

    @property
    def npm(self):
        return os.path.join(self.prefix, 'node', 'bin', 'npm')

    @property
    def entry(self):
        return os.path.join(self.prefix, 'app', 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js')

    @property
    def desktop(self):
        return os.path.join(self.prefix, 'bin', 'dsh-desktop')

    @property
    def share(self):
        return os.path.join(self.prefix, 'share')

    @property
    def install_json(self):
        return os.path.join(self.prefix, 'install.json')

    def url(self):
        return 'http://127.0.0.1:%d' % self.port

    # ---- 状态 ----
    def installed(self):
        return os.path.exists(self.entry) and os.path.exists(self.node)

    def running_pid(self):
        try:
            with open(self.pidfile, 'r', encoding='utf-8') as fh:
                pid = int(fh.read().strip() or 0)
        except Exception:
            return 0
        if pid <= 0:
            return 0
        try:
            os.kill(pid, 0)
            return pid
        except OSError:
            return 0

    def serving(self):
        code, body = probe(self.url() + '/')
        if code == 200 and '__DSH_BOOT__' in body:
            return 'ready'
        if code == 401 or 'dsh web authentication required' in body:
            return 'auth'
        return ''

    # ---- WebUI 入口地址（带 token）----
    # 说明：dsh >=0.1.5 的 WebUI 要认证，裸地址 http://127.0.0.1:<port>/ 只会回一张
    # "authentication required" 的页面。真正的入口是 `dsh web` 启动时打印的那条
    #   dsh web: http://127.0.0.1:3080/?token=xxxx
    # 打开一次之后服务端会种下 cookie，同一浏览器此后可以直接用裸地址。
    # token 等价于密码：界面展示归展示，**不要写进 manager.log**。
    AUTH_LINE = re.compile(r'dsh web:\s*(https?://[^\s]+)')

    def auth_log_candidates(self):
        """可能记录了入口地址的日志文件（按"服务是谁起的"分两处）。"""
        state = os.path.join(os.environ.get('XDG_STATE_HOME')
                             or os.path.expanduser('~/.local/state'),
                             'dsh-desktop', 'logs')
        names = ('web.log', 'server.out.log', 'server.err.log', 'desktop.log')
        out = [os.path.join(self.prefix, 'logs', n) for n in names]
        out += [os.path.join(state, n) for n in ('web.log', 'desktop.log')]
        return out

    def web_auth_url(self):
        """从日志里找**最新**一条带 token 的入口地址。

        返回 (url, 来源文件, 说明)。找不到时 url 为 None，说明里写清原因。
        """
        best_mtime, best_url, best_path = -1.0, '', ''
        for path in self.auth_log_candidates():
            try:
                st = os.stat(path)
                if st.st_size <= 0:
                    continue
                found = None
                with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                    # 日志可能很大：只读尾部 256 KB，避免把界面卡住
                    if st.st_size > 262144:
                        fh.seek(st.st_size - 262144)
                        fh.readline()            # 丢掉可能被截断的半行
                    for line in fh:
                        m = self.AUTH_LINE.search(line)
                        if m:
                            found = m.group(1)
            except OSError:
                continue
            if found and st.st_mtime >= best_mtime:
                best_mtime, best_url, best_path = st.st_mtime, found, path
        if not best_url:
            return None, '', ('日志里没有带 token 的入口地址：'
                              '服务可能还没被启动过，或者日志被清空了。'
                              '先「启动服务」，再点一次「查看 Token」。')
        return best_url, best_path, '已取到最新的一条入口地址'

    def auth_url_status(self, url, timeout=4.0):
        """这条地址现在还有效吗？返回 (状态, 说明)。

        200 = 可用；401 = token 过期（服务重启过）；'' = 连不上（服务没在跑）。
        """
        try:
            code, body = probe(url, timeout=timeout)
        except Exception as exc:
            return '', '请求失败：%s' % exc
        if code == 200:
            return 'ok', 'HTTP 200，地址可用'
        if code == 401 or 'authentication required' in (body or ''):
            return 'expired', 'HTTP 401 —— 这个 token 已过期（服务重启过），重启服务后再看'
        if code == 0:
            return '', '连不上（服务没在运行？）'
        return '', 'HTTP %s，不像是入口地址' % code

    def status(self):
        pid = self.running_pid()
        srv = self.serving() if pid else (self.serving() if self.installed() else '')
        if pid and srv:
            return 'running'
        if pid:
            return 'starting'
        if srv:
            return 'external'          # 不是本管理器起的，但端口上有服务
        return 'stopped' if self.installed() else 'broken'

    def to_dict(self):
        return {
            'prefix': self.prefix,
            'label': self.label,
            'port': self.port,
            'dsh': self.dsh_version,
            'node': self.node_version,
            'dshHome': self.dsh_home,
            'status': self.status(),
            'pid': self.running_pid(),
        }

    # ---- 动作 ----
    def env(self):
        env = dict(os.environ)
        env['PATH'] = '%s:%s:%s:%s' % (
            os.path.join(self.prefix, 'node', 'bin'),
            os.path.join(self.prefix, 'app', 'node_modules', '.bin'),
            os.path.join(self.prefix, 'tools', 'node_modules', '.bin'),
            env.get('PATH', ''))
        env['DSH_HOME'] = self.dsh_home
        env['DSH_PREFIX'] = self.prefix
        env['DSH_SHARE'] = self.share
        env['DSH_BIN'] = self.entry
        env['DSH_WEB_URL'] = self.url()
        return env

    def start(self, wait=90):
        """后台起服务（不依赖管理器进程活着）。返回 (ok, message)。"""
        if not self.installed():
            return False, '实例不完整（缺 node 或 dsh），请先修复'
        if self.serving():
            return True, '服务已在运行'
        os.makedirs(os.path.dirname(self.logfile), exist_ok=True)
        log = open(self.logfile, 'ab', buffering=0)
        args = [self.node, self.entry, 'web', '--no-open', '--port', str(self.port)]
        proc = subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                env=self.env(), start_new_session=True)
        try:
            with open(self.pidfile, 'w', encoding='utf-8') as fh:
                fh.write(str(proc.pid))
        except Exception:
            pass
        deadline = time.time() + wait
        while time.time() < deadline:
            if self.serving():
                return True, '服务已就绪（PID %d，端口 %d）' % (proc.pid, self.port)
            if proc.poll() is not None:
                return False, '服务启动后立即退出，见日志：%s' % self.logfile
            time.sleep(0.8)
        return False, '服务在 %d 秒内没就绪，见日志：%s' % (wait, self.logfile)

    def stop(self):
        pid = self.running_pid()
        if not pid:
            return False, '没有本管理器记录的运行中进程'
        try:
            os.kill(pid, 15)
            for _ in range(20):
                time.sleep(0.2)
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
            else:
                os.kill(pid, 9)
        except OSError as exc:
            return False, '停止失败：%s' % exc
        try:
            os.remove(self.pidfile)
        except Exception:
            pass
        return True, '已停止（PID %d）' % pid

    # ---- 窗口：唤起 / 检测 / 清理 / 重试 ----
    def control_socket(self):
        """窗口进程的控制套接字路径（与 dsh-desktop.py 里的规则一致）。"""
        base = os.environ.get('XDG_RUNTIME_DIR') or '/tmp'
        try:
            uid = os.getuid()
        except Exception:
            uid = 0
        return os.path.join(base, 'dsh-desktop-%d.sock' % uid)

    def _sock_request(self, cmd, timeout=1.5):
        """给窗口进程发一条命令，返回应答文本；连不上返回 ''。"""
        family = getattr(socket, 'AF_UNIX', None)
        if family is None:            # 极少数平台没有 AF_UNIX：当作"没有窗口"
            return ''
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            sock.connect(self.control_socket())
            sock.sendall((cmd + '\n').encode('utf-8'))
            return sock.recv(128).decode('utf-8', 'replace').strip()
        except Exception:
            return ''
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def window_alive(self):
        """窗口是否在跑（能应答 ping）。返回 PID，0 表示没有可用窗口。"""
        resp = self._sock_request('ping')
        if resp.startswith('ok'):
            try:
                return int(resp.split()[1])
            except Exception:
                return -1
        return 0

    def raise_window(self):
        """把已有窗口提到前台（正是"点了打开窗口却没反应"该做的事）。

        唤起之后顺手要一次整窗重绘：软件渲染下窗口从托盘/最小化回来时，
        WebKit 可能只重绘局部，留下一大块没画过的灰带（实测见过）。
        """
        if not self._sock_request('raise').startswith('raised'):
            return False
        self._sock_request('repaint', timeout=0.8)
        return True

    def reload_page(self):
        """让窗口重新加载页面（页面脚本把布局搞坏时的最小动作）。"""
        return self._sock_request('reload', timeout=2.0).startswith('reloaded')

    def repaint_window(self):
        """强制整窗重绘（不改页面，不动会话）。"""
        return self._sock_request('repaint', timeout=2.0).startswith('repainted')

    def _window_pids(self):
        """找属于本实例、但已经不可控的窗口进程（旧版没有控制套接字）。"""
        marker = os.path.join(self.share, 'dsh-desktop.py')
        pids = []
        try:
            entries = os.listdir('/proc')
        except OSError:
            return pids
        for name in entries:
            if not name.isdigit():
                continue
            try:
                with open('/proc/%s/cmdline' % name, 'rb') as fh:
                    cmd = fh.read().decode('utf-8', 'replace')
            except OSError:
                continue
            if marker in cmd:
                pids.append(int(name))
        return pids

    def kill_stale_windows(self, wait=3.0):
        """清掉无响应的窗口进程（只针对本实例的），返回被处理的 PID 列表。"""
        pids = self._window_pids()
        if not pids:
            return []
        for pid in pids:
            try:
                os.kill(pid, 15)          # 先礼貌地 SIGTERM
            except OSError:
                pass
        deadline = time.time() + wait
        while time.time() < deadline:
            if not [p for p in pids if os.path.exists('/proc/%d' % p)]:
                return pids
            time.sleep(0.2)
        for pid in pids:
            if os.path.exists('/proc/%d' % pid):
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass
        return pids

    @staticmethod
    def clear_stale_locks():
        """删掉/清空单实例锁：窗口进程其实已经不在时，它只会挡住下一次启动。"""
        removed = []
        for path in ('/tmp/dsh-desktop.lock', '/tmp/dsh-desktop.lock.pid'):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    removed.append(path)
            except OSError:
                pass
        lockdir = '/tmp/dsh-desktop.lock.d'
        if os.path.isdir(lockdir):
            shutil.rmtree(lockdir, ignore_errors=True)
            removed.append(lockdir)
        return removed

    def _spawn_launcher(self, logpath, settle=8.0, force=False, gl=None):
        """起一次启动器，并用控制套接字判断窗口真的起来了没有。"""
        os.makedirs(os.path.dirname(logpath), exist_ok=True)
        env = self.env()
        if force:
            env['DSH_DESKTOP_FORCE'] = '1'
        if gl:
            env['DSH_DESKTOP_GL'] = gl
        fh = open(logpath, 'ab', buffering=0)
        try:
            proc = subprocess.Popen([self.desktop], env=env, start_new_session=True,
                                    stdout=fh, stderr=fh, stdin=subprocess.DEVNULL)
        except Exception as exc:
            return False, '启动失败：%s' % exc
        finally:
            try:
                fh.close()
            except Exception:
                pass

        deadline = time.time() + max(1.0, settle)
        while time.time() < deadline:
            if self.window_alive():
                return True, '窗口已打开'
            if proc.poll() is not None:
                break
            time.sleep(0.25)
        if self.window_alive():
            return True, '窗口已打开'
        return False, '启动器退出码 %s' % proc.poll()

    def open_window(self, settle=8.0, rebuild=False):
        """打开窗口：先唤起已有窗口；没有则清理旧现场、必要时强制+软件渲染重试。

        rebuild=True 表示「重建窗口」：即使控件套接字还活着也先杀掉重开——
        窗口进程活着但画面坏掉（上半截空白）时，唤起是修不好的。
        """
        if not os.path.exists(self.desktop):
            return False, '缺少启动器：%s（试试「修复」）' % self.desktop
        logpath = os.path.join(self.prefix, 'logs', 'desktop.log')

        if rebuild:
            notes = ['按「重建窗口」处理']
            killed = self.kill_stale_windows()
            if killed:
                notes.append('结束窗口进程 %s' % ', '.join(str(p) for p in killed))
            else:
                notes.append('没有可结束的窗口进程')
            locks = self.clear_stale_locks()
            if locks:
                notes.append('清理旧锁 %d 个' % len(locks))
            ok, msg = self._spawn_launcher(logpath, settle)
            if ok:
                return True, ' '.join(notes)
            ok, msg2 = self._spawn_launcher(logpath, settle, force=True, gl='off')
            if ok:
                notes.append('已用「强制 + 软件渲染」重试成功')
                return True, ' '.join(notes)
            tail = self._tail(logpath, 900)
            return False, ('重建失败（%s）。日志：%s\n%s'
                           % (' / '.join(notes) or msg2, logpath, tail))

        # 1) 已经有窗口：提到前台（这才是"再点一次"该有的行为）
        pid = self.window_alive()
        if pid:
            if self.raise_window():
                return True, '已把现有窗口提到前台（PID %s）' % pid
            return True, ('窗口进程在（PID %s），但它没响应唤起请求'
                          '（可能是旧版窗口，点「修复」后重开即可）' % pid)

        # 2) 没有可用窗口却还占着锁/留着僵死进程：清掉
        notes = []
        killed = self.kill_stale_windows()
        if killed:
            notes.append('清掉无响应的窗口进程 %s' % ', '.join(str(p) for p in killed))
        locks = self.clear_stale_locks()
        if locks:
            notes.append('清理旧锁 %d 个' % len(locks))

        # 3) 正常起一次
        ok, msg = self._spawn_launcher(logpath, settle)
        if ok:
            return True, ' '.join(filter(None, [msg] + notes))

        # 4) 措施：跳过单实例检查 + 强制软件渲染再试一次（虚拟机常见）
        ok, msg2 = self._spawn_launcher(logpath, settle, force=True, gl='off')
        if ok:
            notes.append('已用「强制 + 软件渲染」重试成功')
            return True, ' '.join(notes)
        tail = self._tail(logpath, 900)
        return False, ('窗口没能启动（%s）。日志：%s\n%s'
                       % (' / '.join(notes) or msg2, logpath, tail))

    @staticmethod
    def _tail(path, limit=1200):
        try:
            with open(path, 'rb') as fh:
                data = fh.read()
        except OSError:
            return ''
        text = data.decode('utf-8', 'replace').strip()
        return text[-limit:] if text else ''


# --------------------------------------------------------------------------- 管理器
class Manager:
    def __init__(self, root=None, config_dir=None):
        self.root = os.path.abspath(os.path.expanduser(
            root or os.environ.get('DSH_MANAGER_ROOT') or DEFAULT_ROOT))
        self.config_dir = config_dir or os.path.join(
            os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), APP)
        self.registry = os.path.join(self.config_dir, 'instances.json')
        self._log = []

    # ---- 日志（GUI 用它显示）----
    def log(self, line):
        self._log.append(line)
        if os.environ.get('DSH_MANAGER_VERBOSE') == '1':
            print(line, flush=True)

    def take_log(self):
        lines = list(self._log)
        self._log.clear()
        return lines

    # ---- 注册表 ----
    def _read_registry(self):
        try:
            with open(self.registry, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    def _write_registry(self, entries):
        os.makedirs(self.config_dir, exist_ok=True)
        tmp = self.registry + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(entries, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.registry)

    def _remember(self, inst):
        entries = [e for e in self._read_registry() if e.get('prefix') != inst.prefix]
        entries.append({
            'prefix': inst.prefix, 'label': inst.label, 'port': inst.port,
            'dsh': inst.dsh_version, 'node': inst.node_version, 'dshHome': inst.dsh_home,
        })
        self._write_registry(entries)

    def _forget(self, prefix):
        self._write_registry([e for e in self._read_registry() if e.get('prefix') != prefix])

    # ---- 列实例 ----
    def list_instances(self):
        found = {}
        for entry in self._read_registry():
            prefix = entry.get('prefix')
            if prefix and os.path.isdir(prefix):
                found[prefix] = entry
        # 扫描常见根目录，发现用 install.sh 装过 / 以前装的实例
        roots = [self.root, os.path.expanduser('~/.local/opt'),
                 os.path.expanduser('~/.local/share')]
        for base in roots:
            if not os.path.isdir(base):
                continue
            for name in sorted(os.listdir(base)):
                prefix = os.path.join(base, name)
                if prefix in found or not os.path.isdir(prefix):
                    continue
                if os.path.exists(os.path.join(prefix, 'app', 'package.json')):
                    try:
                        with open(os.path.join(prefix, 'install.json'), 'r', encoding='utf-8') as fh:
                            meta = json.load(fh)
                    except Exception:
                        meta = {'label': name, 'port': 3080}
                    meta.setdefault('label', name)
                    found[prefix] = meta
        out = []
        for prefix, meta in sorted(found.items(), key=lambda kv: kv[0]):
            out.append(Instance(prefix, meta))
        return out

    def next_port(self, start=3080):
        used = {i.port for i in self.list_instances()}
        port = start
        while port < 65535 and (port in used or not port_free(port)):
            port += 1
        return port

    def instance_at(self, prefix):
        prefix = os.path.abspath(os.path.expanduser(prefix))
        meta = {}
        try:
            with open(os.path.join(prefix, 'install.json'), 'r', encoding='utf-8') as fh:
                meta = json.load(fh)
        except Exception:
            for entry in self._read_registry():
                if entry.get('prefix') == prefix:
                    meta = entry
        return Instance(prefix, meta)

    # ---- 版本清单 ----
    def _registry_versions(self):
        """返回 (versions, dist_tags)；取不到就都回空。"""
        try:
            with urllib.request.urlopen('https://registry.npmjs.org/' + NPM_PKG.replace('/', '%2F'),
                                        timeout=8) as r:
                data = json.load(r)
            versions = [v for v in (data.get('versions') or {}).keys()
                        if re.match(r'^\d+\.\d+\.\d+', v)]
            return versions, (data.get('dist-tags') or {})
        except Exception:
            return [], {}

    def available_dsh_versions(self, limit=12):
        versions, tags = self._registry_versions()
        if not versions:
            return list(FALLBACK_DSH_VERSIONS)
        out = []
        latest = tags.get('latest')
        if latest:
            out.append(latest)
        versions.sort(key=_semver_key, reverse=True)
        out.extend([v for v in versions if v not in out])
        return out[:limit] or list(FALLBACK_DSH_VERSIONS)

    def latest_dsh_version(self):
        """latest 的语义（用户定义）：**非 alpha 的最新版**——rc 算，alpha 不算。

        优先用官方 dist-tags.latest（发布者的选择），若它带 alpha 才退回按版本号挑。
        """
        versions, tags = self._registry_versions()
        cand = tags.get('latest')
        if cand and 'alpha' not in cand.lower():
            return cand
        non_alpha = [v for v in versions if 'alpha' not in v.lower()]
        if non_alpha:
            return sorted(non_alpha, key=_semver_key)[-1]
        return DEFAULT_DSH

    def available_node_versions(self):
        try:
            with urllib.request.urlopen('https://nodejs.org/dist/index.json', timeout=8) as r:
                data = json.load(r)
            lts = [d['version'].lstrip('v') for d in data if d.get('lts')]
            seen = []
            for v in lts:
                major = v.split('.')[0]
                if major not in [s.split('.')[0] for s in seen]:
                    seen.append(v)
            return seen[:4] or list(FALLBACK_NODE_VERSIONS)
        except Exception:
            return list(FALLBACK_NODE_VERSIONS)

    def latest_node_version(self):
        """最新的 Node LTS（内置清单里排第一的那个）。"""
        return (self.available_node_versions() or [DEFAULT_NODE])[0]

    # ---- 安装 / 更新 / 修复 / 卸载 ----
    def _download(self, url, dest):
        self.log('下载 %s' % url)
        tmp = dest + '.part'
        with urllib.request.urlopen(url, timeout=600) as r, open(tmp, 'wb') as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        os.replace(tmp, dest)

    def _install_node(self, inst, version):
        node_dir = os.path.join(inst.prefix, 'node')
        tag = arch_tag()
        tarball = '/tmp/dsh-manager-node-%s-%s.tar.xz' % (version, tag)
        if not os.path.exists(tarball):
            self._download('https://nodejs.org/dist/v%s/node-v%s-%s.tar.xz' % (version, version, tag), tarball)
        if os.path.isdir(node_dir):
            shutil.rmtree(node_dir, ignore_errors=True)
        os.makedirs(node_dir, exist_ok=True)
        self.log('解压 Node %s' % version)
        subprocess.run(['tar', '-xJf', tarball, '-C', node_dir, '--strip-components=1'], check=True)

    def _write_launchers(self, inst):
        bin_dir = os.path.join(inst.prefix, 'bin')
        os.makedirs(bin_dir, exist_ok=True)
        node_bin = os.path.join(inst.prefix, 'node', 'bin')
        app_bin = os.path.join(inst.prefix, 'app', 'node_modules', '.bin')
        tools_bin = os.path.join(inst.prefix, 'tools', 'node_modules', '.bin')
        common = (
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'export PATH="%s:%s:%s:$PATH"\n'
            'export DSH_HOME="${DSH_HOME:-%s}"\n' % (node_bin, app_bin, tools_bin, inst.dsh_home))
        with open(os.path.join(bin_dir, 'dsh'), 'w', encoding='utf-8') as fh:
            fh.write(common + 'exec "%s" "%s" "$@"\n' % (inst.node, inst.entry))
        with open(os.path.join(bin_dir, 'dsh-desktop'), 'w', encoding='utf-8') as fh:
            fh.write(common + (
                'export DSH_PREFIX="%s"\nexport DSH_SHARE="%s"\nexport DSH_BIN="%s"\n'
                'export DSH_WEB_URL="${DSH_WEB_URL:-%s}"\n'
                'exec "%s" "$@"\n') % (inst.prefix, inst.share, inst.entry, inst.url(),
                                       os.path.join(inst.share, 'dsh-desktop')))
        for name in ('dsh', 'dsh-desktop'):
            p = os.path.join(bin_dir, name)
            os.chmod(p, 0o755)

    def _provision_share(self, inst):
        """把窗口文件（dsh-desktop.py / 启动器 / preview-tools.js / 图标）放进实例的 share/。"""
        os.makedirs(inst.share, exist_ok=True)
        src_dirs = [SYSTEM_SHARE, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'share')]
        wanted = ['dsh-desktop.py', 'dsh-desktop', 'preview-tools.js', 'dsh-desktop.png']
        for name in wanted:
            dest = os.path.join(inst.share, name)
            for base in src_dirs:
                cand = os.path.join(base, name)
                if os.path.exists(cand):
                    shutil.copy2(cand, dest)
                    if name in ('dsh-desktop', 'dsh-desktop.py'):
                        os.chmod(dest, 0o755)
                    break

    def _approve_scripts(self, inst, force=False):
        """npm 11 默认把依赖的 install scripts 拦下来（allow-scripts 提示）。

        不批准的话 node-pty / koffi 这类原生依赖不会被编译，「终端」工具会报错
        （实测 0.2.x 装完会留 5 个 pending：dsh-subprocess-local / koffi / node-pty /
        @google/genai / protobufjs）。这里显式全部批准并重建，失败只记日志——
        它只影响终端/原生模块，不影响聊天与文件功能。旧版 npm 没有这个命令，跳过即可。
        """
        app = os.path.join(inst.prefix, 'app')
        pkg = os.path.join(app, 'package.json')
        if not force:
            try:
                with open(pkg, 'r', encoding='utf-8') as fh:
                    if 'allowScripts' in json.load(fh):
                        return
            except Exception:
                pass
        for args, label in ((['approve-scripts', '--all'], '批准依赖脚本'),
                            (['rebuild'], '重建原生模块')):
            try:
                proc = subprocess.run([inst.npm] + args, cwd=app, env=inst.env(),
                                      capture_output=True, text=True,
                                      stdin=subprocess.DEVNULL, timeout=1800)
            except Exception as exc:
                self.log('跳过「%s」：%s' % (label, exc))
                continue
            if proc.returncode != 0:
                tail = ((proc.stderr or '') or (proc.stdout or ''))[-400:].strip()
                self.log('「%s」失败（不影响聊天，可能影响终端工具）：%s' % (label, tail))
            elif args[0] == 'approve-scripts':
                self.log('已批准依赖的 install scripts')

    def _npm_install(self, inst, dsh_version):
        app = os.path.join(inst.prefix, 'app')
        os.makedirs(app, exist_ok=True)
        with open(os.path.join(app, 'package.json'), 'w', encoding='utf-8') as fh:
            json.dump({
                'name': 'deepseek-harness-portable', 'private': True,
                'dependencies': {NPM_PKG: dsh_version},
            }, fh, indent=2)
        self.log('安装 %s@%s（npm，进了实例目录）' % (NPM_PKG, dsh_version))
        # stdin=DEVNULL 很关键：npm 11 的 allow-scripts 提示在没有 TTY 时会一直等输入
        # （之前在 WSL 里就因为捕获输出 + 无 stdin 卡了 7 分钟）
        proc = subprocess.run([inst.npm, 'install', '--no-audit', '--no-fund', '--loglevel=error'],
                              cwd=app, env=inst.env(), capture_output=True, text=True,
                              stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or '')[-1200:]
            raise RuntimeError('npm 安装失败：%s' % tail)
        self._approve_scripts(inst)
        # pnpm 单独放 tools/（dsh plugin 会用到）
        tools = os.path.join(inst.prefix, 'tools')
        os.makedirs(tools, exist_ok=True)
        with open(os.path.join(tools, 'package.json'), 'w', encoding='utf-8') as fh:
            json.dump({'name': 'dsh-portable-tools', 'private': True,
                       'dependencies': {'pnpm': '9.15.0'}}, fh, indent=2)
        subprocess.run([inst.npm, 'install', '--no-audit', '--no-fund', '--loglevel=error'],
                       cwd=tools, env=inst.env(), capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)

    def _write_meta(self, inst):
        meta = {
            'prefix': inst.prefix, 'label': inst.label, 'port': inst.port,
            'dsh': inst.dsh_version, 'node': inst.node_version,
            'dshHome': inst.dsh_home, 'installedAt': now_iso(),
            'manager': MANAGER_VERSION,
        }
        with open(inst.install_json, 'w', encoding='utf-8') as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
        inst.meta = meta
        self._remember(inst)

    def install(self, prefix, dsh_version=None, node_version=None, port=None, label=None):
        """新建（或补齐）一个实例。返回 (ok, message, instance)。"""
        if dsh_version == 'latest':
            dsh_version = self.latest_dsh_version()
            self.log('latest → dsh %s' % dsh_version)
        if node_version == 'latest':
            node_version = self.latest_node_version()
            self.log('latest → Node %s' % node_version)
        dsh_version = dsh_version or DEFAULT_DSH
        node_version = node_version or DEFAULT_NODE
        prefix = os.path.abspath(os.path.expanduser(prefix))
        if os.path.exists(prefix) and not os.path.isdir(prefix):
            return False, '目标路径已存在且不是目录：%s' % prefix, None
        inst = Instance(prefix, {'label': label or os.path.basename(prefix),
                                 'port': int(port or self.next_port()),
                                 'dsh': dsh_version, 'node': node_version,
                                 'dshHome': os.path.join(prefix, 'dsh-home')})
        try:
            os.makedirs(inst.prefix, exist_ok=True)
            for sub in ('bin', 'share', 'logs', 'dsh-home'):
                os.makedirs(os.path.join(inst.prefix, sub), exist_ok=True)
            self.log('实例目录：%s' % inst.prefix)

            have_node = os.path.exists(inst.node)
            if not have_node:
                self._install_node(inst, node_version)
            else:
                self.log('复用已有 Node：%s' % inst.node)

            self._npm_install(inst, dsh_version)
            if not os.path.exists(inst.entry):
                raise RuntimeError('安装后仍找不到 dsh 入口：%s' % inst.entry)

            self._provision_share(inst)
            inst.dsh_version = dsh_version
            inst.node_version = node_version
            self._write_launchers(inst)
            self._write_meta(inst)
            self.log('✔ 安装完成：%s' % inst.prefix)
            return True, '安装完成：%s（端口 %d）' % (inst.prefix, inst.port), inst
        except Exception as exc:
            self.log('✘ 安装失败：%s' % exc)
            return False, '安装失败：%s' % exc, inst

    def update(self, prefix, dsh_version=None, node_version=None):
        inst = self.instance_at(prefix)
        if not inst.installed():
            return False, '实例不完整，请先「修复」', inst
        if dsh_version == 'latest':
            dsh_version = self.latest_dsh_version()
            self.log('latest → dsh %s' % dsh_version)
        if node_version == 'latest':
            node_version = self.latest_node_version()
            self.log('latest → Node %s' % node_version)
        dsh_version = dsh_version or inst.dsh_version or DEFAULT_DSH
        node_version = node_version or inst.node_version or DEFAULT_NODE
        try:
            if node_version != inst.node_version or not os.path.exists(inst.node):
                self._install_node(inst, node_version)
            self._npm_install(inst, dsh_version)
            inst.dsh_version = dsh_version
            inst.node_version = node_version
            self._provision_share(inst)
            self._write_launchers(inst)
            self._write_meta(inst)
            return True, '已更新到 dsh %s / node %s' % (dsh_version, node_version), inst
        except Exception as exc:
            return False, '更新失败：%s' % exc, inst

    def open_window(self, prefix, rebuild=False):
        """打开实例窗口：先确保实例里的窗口程序是本包版本，再交给实例的逻辑。

        实例的 share/ 只在「安装 / 更新 / 修复」时刷新；管理器升级后，
        旧实例里还是旧启动器（例如不懂控制套接字的老版本）。这里顺手对齐，
        省得用户每次都要点一次「修复」。

        rebuild=True：窗口活着也要重开（画面坏掉时唤起修不好）。
        """
        inst = self.instance_at(prefix)
        refreshed = self._refresh_share_if_stale(inst)
        ok, msg = inst.open_window(rebuild=rebuild)
        if refreshed and ok:
            if '提到前台' in msg:
                # 程序文件换了，但正在跑的那个窗口进程还是旧的（它不懂 reload/repaint）。
                # 这里必须说清楚，否则用户会以为"装了新版也没用"。
                msg = msg + ('（实例的窗口程序已更新，但当前窗口仍是旧进程，'
                             '新功能要点「重建窗口」才会生效）')
            else:
                msg = msg + '（已顺手把实例的窗口程序更新到本包版本）'
        return ok, msg, inst

    def _refresh_share_if_stale(self, inst):
        """实例里的 dsh-desktop / dsh-desktop.py 与本包不一致时刷新。"""
        changed = False
        for name in ('dsh-desktop', 'dsh-desktop.py'):
            src = os.path.join(SYSTEM_SHARE, name)
            dst = os.path.join(inst.share, name)
            if not (os.path.exists(src) and os.path.exists(dst)):
                continue
            try:
                with open(src, 'rb') as a, open(dst, 'rb') as b:
                    if a.read() != b.read():
                        changed = True
                        break
            except OSError:
                continue
        if changed:
            try:
                self._provision_share(inst)
            except Exception:
                pass
        return changed

    def repair(self, prefix):
        """修复：补齐缺失的 node / dsh / share / 启动器，并校验服务能启动。"""
        inst = self.instance_at(prefix)
        steps = []
        try:
            for sub in ('bin', 'share', 'logs', 'dsh-home'):
                os.makedirs(os.path.join(inst.prefix, sub), exist_ok=True)
            if not os.path.exists(inst.node):
                self._install_node(inst, inst.node_version or DEFAULT_NODE)
                steps.append('重装 Node')
            if not os.path.exists(inst.entry):
                self._npm_install(inst, inst.dsh_version or DEFAULT_DSH)
                steps.append('重装 dsh')
            self._approve_scripts(inst)
            self._provision_share(inst)
            steps.append('刷新窗口文件')
            self._write_launchers(inst)
            steps.append('重写启动器')
            self._write_meta(inst)
            if not os.access(inst.prefix, os.W_OK):
                raise RuntimeError('实例目录不可写')
            return True, '修复完成：' + '、'.join(steps), inst
        except Exception as exc:
            return False, '修复失败：%s' % exc, inst

    def uninstall(self, prefix, purge_data=False):
        inst = self.instance_at(prefix)
        try:
            inst.stop()
        except Exception:
            pass
        try:
            if purge_data:
                shutil.rmtree(inst.prefix, ignore_errors=False)
            else:
                shutil.rmtree(inst.prefix, ignore_errors=False)
        except Exception as exc:
            return False, '删除失败：%s' % exc
        self._forget(inst.prefix)
        return True, '已卸载：%s' % inst.prefix
