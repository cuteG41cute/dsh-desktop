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
MANAGER_VERSION = '1.0.0'


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

    def open_window(self):
        """用实例自带的 dsh-desktop 打开窗口（它会复用已在跑的服务）。"""
        if not os.path.exists(self.desktop):
            return False, '缺少启动器：%s（试试「修复」）' % self.desktop
        try:
            subprocess.Popen([self.desktop], env=self.env(), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, '已打开窗口'
        except Exception as exc:
            return False, '打开失败：%s' % exc


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
    def available_dsh_versions(self, limit=12):
        out = []
        try:
            with urllib.request.urlopen('https://registry.npmjs.org/' + NPM_PKG.replace('/', '%2F'),
                                        timeout=8) as r:
                data = json.load(r)
            versions = [v for v in (data.get('versions') or {}).keys()
                        if re.match(r'^\d+\.\d+\.\d+', v)]
            latest = data.get('dist-tags', {}).get('latest')
            def key(v):
                parts = re.findall(r'\d+', v)[:3]
                return [int(p) for p in parts] + [0 if '-' in v else 1]
            versions.sort(key=key, reverse=True)
            if latest:
                out.append(latest)
            out.extend([v for v in versions if v not in out])
        except Exception:
            out = list(FALLBACK_DSH_VERSIONS)
        return out[:limit] or list(FALLBACK_DSH_VERSIONS)

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
