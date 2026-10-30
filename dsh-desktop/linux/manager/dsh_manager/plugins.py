# -*- coding: utf-8 -*-
"""实例的插件管理（第一阶段）：从我们自己的 GitHub 仓库安装 / 卸载插件。

一个 DSH 插件"装进某个实例"= 两件事（照抄手工安装的结构）：

1. 包体放进 ``<实例>/dsh-home/profiles/web/node_modules/<包名>/``
2. 在 ``<实例>/dsh-home/profiles/web/cordis.patch.yml`` 里追加一条
   ``- insert:`` 记录（``id`` / ``name`` / 可选 ``inject``）

包体来源：GitHub 仓库的 tarball。端点按顺序试（实测三个都通，取最快的能用的）：

* ``https://api.github.com/repos/<owner>/<repo>/tarball/<ref>``  ← 通常可用（API 域名不被墙）
* ``https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/<ref>``
* 本地缓存 ``~/.config/dsh-manager/plugin-cache/<id>-<ref>.tar.gz``（离线/内网可用）

包里可能有多个 package.json（例如根目录是"动态版"、`static/` 才是"常驻版"），
所以按这个优先级挑：**带 ``dsh`` 字段的 > 名字与 id 相同的 > 非 private 的**。
"""
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request

MARKER = '# ── installed-by: dsh-manager (%s) ──'

# 我们的插件目录（仓库结构已实测核对：static/ 是常驻版，dsh-api 在 plugin/）
CATALOG = [
    {
        'id': 'dsh-time-stamp',
        'name': '时间戳注入',
        'repo': 'cuteG41cute/dsh-time-stamp',
        'desc': '每条提问前注入一条时钟上下文，按项目可开关',
        'inject': [],
        'hint': 'static',
    },
    {
        'id': 'dsh-memory-db',
        'name': '项目记忆库',
        'repo': 'cuteG41cute/dsh-memory-db',
        'desc': '按关键词召回历史问答并注入当前回合',
        'inject': ['tools'],
        'hint': 'static',
    },
    {
        'id': 'dsh-screenshot',
        'name': '对话内截图与标注',
        'repo': 'cuteG41cute/dsh-screenshot',
        'desc': '截图 / 框选 + 画笔标注，直接进会话附件',
        'inject': [],
        'hint': 'static',
    },
    {
        'id': 'dsh-api',
        'name': 'HTTP 调用接口',
        'repo': 'cuteG41cute/dsh-api',
        'desc': '把 harness 当服务调用（/api/v1/tasks），其他 agent 可遥控',
        'inject': ['webServer'],
        'hint': 'plugin',
    },
]

UA = {'User-Agent': 'dsh-manager'}


# ---------------------------------------------------------------- 路径与小工具
def profile_dir(inst):
    return os.path.join(inst.dsh_home, 'profiles', 'web')


def patch_path(inst):
    return os.path.join(profile_dir(inst), 'cordis.patch.yml')


def node_modules(inst):
    return os.path.join(profile_dir(inst), 'node_modules')


def cache_dir():
    base = os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache')
    return os.path.join(base, 'dsh-manager', 'plugin-cache')


def catalog():
    return [dict(item) for item in CATALOG]


def find(id_):
    for item in CATALOG:
        if item['id'] == id_:
            return dict(item)
    return None


def _read(path, default=''):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read()
    except OSError:
        return default


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(text)
    os.replace(tmp, path)


def package_version(inst, pid):
    pkg = os.path.join(node_modules(inst), pid, 'package.json')
    try:
        with open(pkg, 'r', encoding='utf-8') as fh:
            return json.load(fh).get('version') or ''
    except Exception:
        return ''


def registered_in_patch(inst, pid):
    return (MARKER % pid) in _read(patch_path(inst))


def installed(inst):
    """返回 {id: {'installed': bool, 'version': str, 'registered': bool}}。"""
    out = {}
    for item in CATALOG:
        pid = item['id']
        have_dir = os.path.isdir(os.path.join(node_modules(inst), pid))
        reg = registered_in_patch(inst, pid)
        out[pid] = {
            'installed': have_dir and reg,
            'package_on_disk': have_dir,
            'registered': reg,
            'version': package_version(inst, pid),
        }
    return out


# ---------------------------------------------------------------- patch 文件
def render_block(entry):
    lines = [MARKER % entry['id'], '- insert:', "    - id: %s" % entry['id'],
             "      name: '%s'" % entry['id']]
    inject = entry.get('inject') or []
    if inject:
        lines.append('      inject: [%s]' % ', '.join(inject))
    return '\n'.join(lines) + '\n'


def append_block(inst, entry):
    path = patch_path(inst)
    text = _read(path)
    if (MARKER % entry['id']) in text:
        return False                     # 已经登记过
    if text and not text.endswith('\n'):
        text += '\n'
    _write(path, text + '\n' + render_block(entry))
    return True


def remove_block(inst, pid):
    """删掉我们写的那一块（标记行 + 紧随其后的 - insert: 及其缩进内容）。"""
    path = patch_path(inst)
    text = _read(path)
    marker = MARKER % pid
    if marker not in text:
        return False
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == marker:
            i += 1
            if i < len(lines) and lines[i].lstrip().startswith('- insert:'):
                i += 1
                while i < len(lines) and (not lines[i].strip() or lines[i][:1] in (' ', '\t')):
                    i += 1
            continue
        out.append(lines[i])
        i += 1
    _write(path, '\n'.join(out).rstrip('\n') + '\n')
    return True


# ---------------------------------------------------------------- 下载 / 解包
def _download(urls, dest, log):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last = ''
    for url in urls:
        log('下载 %s' % url)
        tmp = dest + '.part'
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as resp, open(tmp, 'wb') as fh:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    fh.write(chunk)
            if os.path.getsize(tmp) < 512:
                raise RuntimeError('内容过小（%d B）' % os.path.getsize(tmp))
            os.replace(tmp, dest)
            return True, ''
        except Exception as exc:
            last = '%s → %s' % (url, exc)
            try:
                os.remove(tmp)
            except OSError:
                pass
    return False, last or '没有可用地址'


def fetch(entry, ref='main', log=print):
    """拿 tarball：先看缓存，再试两个 GitHub 端点。返回 (路径, 错误)。"""
    dest = os.path.join(cache_dir(), '%s-%s.tar.gz' % (entry['id'], ref))
    if os.path.exists(dest) and os.path.getsize(dest) > 512:
        log('使用缓存 %s' % dest)
        return dest, ''
    owner_repo = entry['repo']
    urls = [
        'https://api.github.com/repos/%s/tarball/%s' % (owner_repo, ref),
        'https://codeload.github.com/%s/tar.gz/refs/heads/%s' % (owner_repo, ref),
    ]
    ok, err = _download(urls, dest, log)
    return (dest if ok else ''), err


def pick_package(root, want_name):
    """在解包目录里挑出真正要装的包（带 dsh 字段的优先）。"""
    candidates = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.git')]
        if 'package.json' not in files:
            continue
        path = os.path.join(base, 'package.json')
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                meta = json.load(fh)
        except Exception:
            continue
        candidates.append({
            'dir': base,
            'name': meta.get('name') or '',
            'version': meta.get('version') or '',
            'has_dsh': bool(meta.get('dsh')),
            'private': bool(meta.get('private')),
            'depth': base[len(root):].count(os.sep),
        })
    if not candidates:
        return None
    def score(c):
        return (
            0 if c['has_dsh'] else 1,
            0 if c['name'] == want_name else 1,
            c['depth'],
        )
    candidates.sort(key=score)
    return candidates[0]


def install(inst, entry, log=print):
    """把插件装进实例。返回 (ok, message)。"""
    if not os.path.isdir(profile_dir(inst)):
        return False, ('实例还没有 profile 目录（%s）。先在管理器里「启动服务」一次，'
                       '让 dsh 初始化数据目录，再装插件。' % profile_dir(inst))
    tarball, err = fetch(entry, log=log)
    if not tarball:
        return False, '下载失败（%s）。可把 tarball 放到 %s 后重试' % (err, cache_dir())
    work = tempfile.mkdtemp(prefix='dsh-plugin-')
    try:
        log('解包 %s' % os.path.basename(tarball))
        with tarfile.open(tarball, 'r:*') as tar:
            tar.extractall(work)
        roots = [d for d in os.listdir(work) if os.path.isdir(os.path.join(work, d))]
        root = os.path.join(work, roots[0]) if roots else work
        picked = pick_package(root, entry['id'])
        if not picked:
            return False, '包里没找到 package.json（仓库结构变了？）'
        log('选中 %s（%s）' % (picked['dir'][len(root):] or '/', picked['name'] or '?'))
        target = os.path.join(node_modules(inst), picked['name'] or entry['id'])
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copytree(picked['dir'], target,
                        ignore=shutil.ignore_patterns('node_modules', '.git', '*.tar.gz'))
        added = append_block(inst, entry)
        ver = picked['version'] or '?'
        log('%s 已安装到 %s%s' % (entry['id'], target,
                                 '' if added else '（patch 里已存在，未重复追加）'))
        return True, ('已安装 %s %s（%s）%s'
                      % (entry['id'], ver, entry['repo'],
                         '，已写入 cordis.patch.yml' if added else '，patch 记录已存在'))
    except Exception as exc:
        return False, '安装失败：%s' % exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def uninstall(inst, entry, log=print):
    pid = entry['id']
    target = os.path.join(node_modules(inst), pid)
    removed_dir = False
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
        removed_dir = True
        log('已删除 %s' % target)
    removed_row = remove_block(inst, pid)
    if removed_row:
        log('已从 cordis.patch.yml 摘除 %s' % pid)
    if not (removed_dir or removed_row):
        return False, '%s 似乎没装过（既没有包目录也没有 patch 记录）' % pid
    return True, '已卸载 %s%s' % (pid, '（重启服务后生效）' if removed_row or removed_dir else '')
