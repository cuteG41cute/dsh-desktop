# -*- coding: utf-8 -*-
"""实例的插件管理：从我们自己的 GitHub 仓库（或本地包）安装 / 卸载插件。

一个 DSH 插件"装进某个实例"= 两件事（照抄手工安装的结构）：

1. 包体放进 ``<实例>/dsh-home/profiles/web/node_modules/<包名>/``
2. 在 ``<实例>/dsh-home/profiles/web/cordis.patch.yml`` 里追加一条
   ``- insert:`` 记录（``id`` / ``name`` / 可选 ``inject``）

来源三种，按可用性依次尝试：

* ``https://api.github.com/repos/<owner>/<repo>/tarball/<ref>``（API 域名，通常不被墙）
* ``https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/<ref>``
* 本地缓存 ``~/.cache/dsh-manager/plugin-cache/<id>-<ref>.tar.gz``（离线 / 内网）
* **本地 tar.gz 导入**（``install_from_tarball``）：没上 GitHub 的插件也能装

一个仓库里可能有多个包（``dsh-mobile`` 仓库里的 ``netmon/`` 就是插件），
所以目录里给每个插件写了 ``subdir``；同时包里若出现多个 package.json，
按「subdir 命中 > 带 ``dsh`` 字段 > 名字与 id 相同 > 浅层」挑。
"""
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request

MARKER = '# ── installed-by: dsh-manager (%s) ──'

# 目录：一个插件一条。subdir 指向仓库里真正的包目录（实测核对过）
CATALOG = [
    {
        'id': 'dsh-time-stamp',
        'name': '时间戳注入',
        'repo': 'cuteG41cute/dsh-time-stamp',
        'subdir': 'static',
        'desc': '每条提问前注入一条时钟上下文，按项目可开关',
        'inject': [],
    },
    {
        'id': 'dsh-memory-db',
        'name': '项目记忆库',
        'repo': 'cuteG41cute/dsh-memory-db',
        'subdir': 'static',
        'desc': '按关键词召回历史问答并注入当前回合',
        'inject': ['tools'],
    },
    {
        'id': 'dsh-screenshot',
        'name': '对话内截图与标注',
        'repo': 'cuteG41cute/dsh-screenshot',
        'subdir': 'static',
        'desc': '截图 / 框选 + 画笔标注，直接进会话附件',
        'inject': [],
    },
    {
        'id': 'dsh-netmon',
        'name': '网络 / 隧道监视',
        'repo': 'cuteG41cute/dsh-mobile',          # 插件在手机项目仓库的 netmon/ 下
        'subdir': 'netmon',
        'desc': '会话头部「网络」芯片：桥健康、内网入口、隧道可达性、证书剩余天数',
        'inject': [],
    },
    {
        'id': 'dsh-api',
        'name': 'HTTP 调用接口',
        'repo': 'cuteG41cute/dsh-api',
        'subdir': 'plugin',
        'desc': '把 harness 当服务调用（/api/v1/tasks），其他 agent 可遥控',
        'inject': ['webServer'],
    },
    # 只存在于本地工作区、还没推 GitHub 的插件：装不上时给一句明确提示
    {
        'id': 'dsh-file-history',
        'name': '改前自动备份',
        'repo': '',
        'subdir': '',
        'desc': '任何写入覆盖前自动快照，可 list / show / restore / revert_turn',
        'inject': ['tools', 'settings', 'timer'],
        'local_only': True,
    },
    {
        'id': 'dsh-butler',
        'name': '管家派活通道',
        'repo': '',
        'subdir': '',
        'desc': '把「真正要动手的活」转交给独立的工作会话（走本机 dsh-api）',
        'inject': [],
        'local_only': True,
    },
    {
        'id': 'dsh-cleaner',
        'name': '会话 / 文件清理',
        'repo': '',
        'subdir': '',
        'desc': '按工作区列出会话与体积，两步确认后删除（进 ~/.dsh/trash）',
        'inject': [],
        'local_only': True,
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


def state_path(inst):
    """记录"这个实例装过哪些插件、从哪来的"（本地导入的也靠它卸载）。"""
    return os.path.join(inst.prefix, 'plugins.json')


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


def load_state(inst):
    try:
        with open(state_path(inst), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(inst, data):
    try:
        _write(state_path(inst), json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass


def package_meta(pkg_dir):
    try:
        with open(os.path.join(pkg_dir, 'package.json'), 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def package_version(inst, pid):
    return package_meta(os.path.join(node_modules(inst), pid)).get('version') or ''


def registered_in_patch(inst, pid):
    return (MARKER % pid) in _read(patch_path(inst))


# ---------------------------------------------------------------- 发现（目录 + 已装）
def _extra_installed(inst):
    """node_modules 里那些"不在目录里但确实装着"的 dsh-* 包 —— 避免漏看。"""
    out = []
    base = node_modules(inst)
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return out
    known = {item['id'] for item in CATALOG}
    for name in names:
        if not name.startswith('dsh-') or name in known:
            continue
        path = os.path.join(base, name)
        if not os.path.isdir(path):
            continue
        meta = package_meta(path)
        out.append({
            'id': name,
            'name': meta.get('description') or name,
            'repo': '',
            'subdir': '',
            'desc': '（不在内置目录里，可能是本地包或其他来源）',
            'inject': [],
            'extra': True,
        })
    return out


def all_entries(inst):
    """目录 + 实例里实际装着的额外插件。"""
    return catalog() + _extra_installed(inst)


def entry_for(inst, pid):
    entry = find(pid)
    if entry:
        return entry
    for item in _extra_installed(inst):
        if item['id'] == pid:
            return item
    return None


def installed(inst):
    """返回 {id: {'installed','package_on_disk','registered','version'}}。"""
    out = {}
    for item in all_entries(inst):
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
        return False
    if text and not text.endswith('\n'):
        text += '\n'
    _write(path, text + '\n' + render_block(entry))
    return True


def remove_block(inst, pid):
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


# ---------------------------------------------------------------- 下载 / 解包 / 选包
def _download(urls, dest, log):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last = ''
    for url in urls:
        log('下载 %s' % url)
        tmp = dest + '.part'
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, 'wb') as fh:
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
    if not entry.get('repo'):
        return '', '这个插件没有 GitHub 仓库（只能用本地包导入）'
    dest = os.path.join(cache_dir(), '%s-%s.tar.gz' % (entry['id'], ref))
    if os.path.exists(dest) and os.path.getsize(dest) > 512:
        log('使用缓存 %s' % dest)
        return dest, ''
    urls = [
        'https://api.github.com/repos/%s/tarball/%s' % (entry['repo'], ref),
        'https://codeload.github.com/%s/tar.gz/refs/heads/%s' % (entry['repo'], ref),
    ]
    ok, err = _download(urls, dest, log)
    return (dest if ok else ''), err


def pick_package(root, want_name, subdir=''):
    """在解包目录里挑出真正要装的包。

    优先级：指定的 subdir 命中 > 带 ``dsh`` 字段 > 名字与 id 相同 > 层级浅。
    """
    wanted_dir = os.path.normpath(os.path.join(root, subdir)) if subdir else ''
    candidates = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.git')]
        if 'package.json' not in files:
            continue
        meta = package_meta(base)
        candidates.append({
            'dir': base,
            'name': meta.get('name') or '',
            'version': meta.get('version') or '',
            'has_dsh': bool(meta.get('dsh')),
            'private': bool(meta.get('private')),
            'depth': base[len(root):].count(os.sep),
            'is_hint': bool(wanted_dir) and os.path.normpath(base) == wanted_dir,
        })
    if not candidates:
        return None
    candidates.sort(key=lambda c: (0 if c['is_hint'] else 1,
                                   0 if c['has_dsh'] else 1,
                                   0 if c['name'] == want_name else 1,
                                   c['depth']))
    return candidates[0]


def _install_dir(inst, entry, picked, log):
    target = os.path.join(node_modules(inst), picked['name'] or entry['id'])
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copytree(picked['dir'], target,
                    ignore=shutil.ignore_patterns('node_modules', '.git', '*.tar.gz'))
    return target


def install(inst, entry, log=print):
    """按目录条目安装（GitHub 或缓存）。返回 (ok, message)。"""
    if not os.path.isdir(profile_dir(inst)):
        return False, ('实例还没有 profile 目录（%s）。先在管理器里「启动服务」一次，'
                       '让 dsh 初始化数据目录，再装插件。' % profile_dir(inst))
    if entry.get('local_only') or not entry.get('repo'):
        return False, ('%s 还没发布到 GitHub，只能本地导入：把仓库打成 .tar.gz 后点'
                       '「导入本地包…」' % entry['id'])
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
        picked = pick_package(root, entry['id'], entry.get('subdir') or '')
        if not picked:
            return False, '包里没找到 package.json（仓库结构变了？）'
        log('选中 %s（%s %s）' % (picked['dir'][len(root):] or '/',
                                 picked['name'] or '?', picked['version'] or '?'))
        target = _install_dir(inst, entry, picked, log)
        added = append_block(inst, entry)
        state = load_state(inst)
        state[entry['id']] = {'repo': entry['repo'], 'subdir': entry.get('subdir') or '',
                              'version': picked['version'] or '', 'source': 'github'}
        save_state(inst, state)
        log('%s 已安装到 %s%s' % (entry['id'], target,
                                 '' if added else '（patch 里已存在，未重复追加）'))
        return True, ('已安装 %s %s（%s/%s）%s'
                      % (entry['id'], picked['version'] or '?', entry['repo'],
                         entry.get('subdir') or '/',
                         '，已写入 cordis.patch.yml' if added else '，patch 记录已存在'))
    except Exception as exc:
        return False, '安装失败：%s' % exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def install_from_tarball(inst, tarball, log=print, inject=None):
    """从本地 .tar.gz 导入（没上 GitHub 的插件走这条）。返回 (ok, message)。"""
    if not os.path.isdir(profile_dir(inst)):
        return False, '实例还没有 profile 目录，先「启动服务」一次再装。'
    if not os.path.isfile(tarball):
        return False, '文件不存在：%s' % tarball
    work = tempfile.mkdtemp(prefix='dsh-plugin-local-')
    try:
        log('解包 %s' % os.path.basename(tarball))
        with tarfile.open(tarball, 'r:*') as tar:
            tar.extractall(work)
        roots = [d for d in os.listdir(work) if os.path.isdir(os.path.join(work, d))]
        root = os.path.join(work, roots[0]) if roots else work
        picked = pick_package(root, '')
        if not picked or not picked['name']:
            return False, '这个包里没找到带 name 的 package.json'
        pid = picked['name']
        entry = find(pid) or {'id': pid, 'inject': list(inject or [])}
        if inject is not None:
            entry = dict(entry)
            entry['inject'] = list(inject)
        target = _install_dir(inst, entry, picked, log)
        added = append_block(inst, entry)
        state = load_state(inst)
        state[pid] = {'repo': entry.get('repo') or '', 'subdir': entry.get('subdir') or '',
                      'version': picked['version'] or '', 'source': 'tarball',
                      'file': os.path.basename(tarball)}
        save_state(inst, state)
        log('%s 已安装到 %s' % (pid, target))
        return True, ('已从本地包导入 %s %s%s'
                      % (pid, picked['version'] or '?',
                         '，已写入 cordis.patch.yml' if added else '，patch 记录已存在'))
    except Exception as exc:
        return False, '导入失败：%s' % exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def uninstall(inst, entry=None, pid=None, log=print):
    """卸载：删包目录 + 摘 patch 记录（目录里没有的也能卸）。"""
    pid = pid or (entry or {}).get('id')
    if not pid:
        return False, '没指定插件 id'
    target = os.path.join(node_modules(inst), pid)
    removed_dir = False
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
        removed_dir = True
        log('已删除 %s' % target)
    removed_row = remove_block(inst, pid)
    if removed_row:
        log('已从 cordis.patch.yml 摘除 %s' % pid)
    state = load_state(inst)
    if pid in state:
        state.pop(pid, None)
        save_state(inst, state)
    if not (removed_dir or removed_row):
        return False, '%s 似乎没装过（既没有包目录也没有 patch 记录）' % pid
    return True, '已卸载 %s（重启服务后生效）' % pid
