# -*- coding: utf-8 -*-
"""项目迁移（Linux 端）：把 DSH 的一个工作空间（目录 + 会话记录 + 注册表条目）
打成 .dshproj（tar.gz），可在另一台机器的管理器里导入。
"""
import json
import os
import shutil
import tarfile
import tempfile
import time
import uuid

SKIP = {'node_modules', '.git', '.dsh-backup', 'bin', 'obj', 'dist', '.vs', '.tmp'}


def dsh_home():
    return os.environ.get('DSH_HOME') or os.path.expanduser('~/.dsh')


def workspace_file():
    return os.path.join(dsh_home(), 'storages', 'workspace.json')


def sessions_root():
    return os.path.join(dsh_home(), 'sessions')


def project_key(cwd):
    """与 DSH 的 projectKey 一致：分隔符折叠成 '-'，不安全字符转 ~XXXX。"""
    out = []
    sep = False
    for ch in cwd:
        if ch in ('/', '\\', ':'):
            if not sep:
                out.append('-')
            sep = True
        elif ch != '~' and (ch.isascii() and (ch.isalnum() or ch in '._-')):
            out.append(ch)
            sep = False
        else:
            out.append('~%04X' % ord(ch))
            sep = False
    body = ''.join(out).lstrip('-') or 'root'
    return '--' + body[:251] + '--'


def list_projects():
    path = workspace_file() if not dsh_home else os.path.join(dsh_home, 'storages', 'workspace.json')
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        ws = (data.get('tables') or {}).get('workspaces') or {}
        out = []
        for wid, item in ws.items():
            out.append({
                'id': wid,
                'path': item.get('path') or '',
                'title': item.get('title') or os.path.basename(item.get('path') or ''),
                'sessions': len(item.get('sessionIds') or []),
            })
        return sorted(out, key=lambda x: x['title'])
    except (OSError, ValueError):
        return []


def _add_dir(tar, root, prefix):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            full = os.path.join(base, name)
            rel = os.path.relpath(full, root).replace('\\', '/')
            try:
                tar.add(full, arcname=prefix + '/' + rel, recursive=False)
            except OSError:
                pass


def export(project, bundle_path, include_files=False, log=None, dsh_home=None):
    path = workspace_file()
    if not os.path.isfile(path):
        return False, '找不到 workspace.json：%s' % path
    tmp = bundle_path + '.tmp'
    manifest = {
        'format': 'dsh-project-v1',
        'title': project['title'],
        'sourcePath': project['path'],
        'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    try:
        if log:
            log('打包中：%s' % project['title'])
        with tarfile.open(tmp, 'w:gz') as tar:
            mpath = os.path.join(tempfile.gettempdir(), 'dshproj-manifest.json')
            with open(mpath, 'w', encoding='utf-8') as fh:
                json.dump(manifest, fh, ensure_ascii=False, indent=2)
            tar.add(mpath, arcname='manifest.json')
            os.remove(mpath)

            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            entry = ((data.get('tables') or {}).get('workspaces') or {}).get(project['id'])
            if entry is not None:
                ep = os.path.join(tempfile.gettempdir(), 'dshproj-entry.json')
                with open(ep, 'w', encoding='utf-8') as fh:
                    json.dump(entry, fh, ensure_ascii=False, indent=2)
                tar.add(ep, arcname='state/workspace-entry.json')
                os.remove(ep)

            key = project_key(project['path'])
            sdir = os.path.join(sessions_root() if not dsh_home else os.path.join(dsh_home, 'sessions'), key)
            if log:
                log('会话目录：%s' % sdir)
            if os.path.isdir(sdir):
                _add_dir(tar, sdir, 'sessions')

            if include_files and os.path.isdir(project['path']):
                if log:
                    log('打包项目文件：%s' % project['path'])
                _add_dir(tar, project['path'], 'project')

        if os.path.exists(bundle_path):
            os.remove(bundle_path)
        os.replace(tmp, bundle_path)
        size = os.path.getsize(bundle_path) / 1024 / 1024
        return True, '已导出「%s」（%.1f MB）' % (project['title'], size)
    except Exception as exc:  # noqa: BLE001
        return False, '导出失败：%s' % exc


def import_bundle(bundle_path, dest_root, log=None, dsh_home=None):
    work = tempfile.mkdtemp(prefix='dshproj-')
    try:
        with tarfile.open(bundle_path, 'r:gz') as tar:
            for member in tar.getmembers():
                target = os.path.realpath(os.path.join(work, member.name))
                if not target.startswith(os.path.realpath(work)):
                    continue
                tar.extract(member, work)
        manifest_path = os.path.join(work, 'manifest.json')
        if not os.path.isfile(manifest_path):
            return False, '包里没有 manifest.json'
        with open(manifest_path, encoding='utf-8') as fh:
            manifest = json.load(fh)
        title = manifest.get('title') or 'imported'

        src_project = os.path.join(work, 'project')
        dest_project = os.path.join(dest_root, title)
        if os.path.isdir(src_project):
            if os.path.exists(dest_project):
                dest_project += '-' + time.strftime('%m%d%H%M')
            os.makedirs(dest_root, exist_ok=True)
            shutil.copytree(src_project, dest_project)
            if log:
                log('项目文件 → %s' % dest_project)
        else:
            os.makedirs(dest_project, exist_ok=True)

        wid = str(uuid.uuid4())
        src_sessions = os.path.join(work, 'sessions')
        session_ids = []
        if os.path.isdir(src_sessions):
            dest_sessions = os.path.join(sessions_root() if not dsh_home else os.path.join(dsh_home, 'sessions'), project_key(dest_project))
            if os.path.isdir(dest_sessions):
                shutil.rmtree(dest_sessions)
            shutil.copytree(src_sessions, dest_sessions)
            session_ids = [d for d in os.listdir(src_sessions)
                           if os.path.isdir(os.path.join(src_sessions, d))]
            if log:
                log('会话 %d 个' % len(session_ids))

        wf = workspace_file() if not dsh_home else os.path.join(dsh_home, 'storages', 'workspace.json')
        if os.path.isfile(wf):
            with open(wf, encoding='utf-8') as fh:
                data = json.load(fh)
        else:
            data = {'unit': {'name': 'workspace', 'version': 2},
                    'global': {'initialized': True, 'workspaceIds': [], 'archivedSessionIds': []},
                    'tables': {'workspaces': {}}}
        tables = data.setdefault('tables', {})
        ws = tables.setdefault('workspaces', {})
        ws[wid] = {'path': dest_project, 'title': title, 'sessionIds': session_ids}
        g = data.setdefault('global', {})
        g.setdefault('workspaceIds', []).append(wid)
        if os.path.isfile(wf):
            shutil.copyfile(wf, wf + '.bak-' + time.strftime('%Y%m%d-%H%M%S'))
        os.makedirs(os.path.dirname(wf), exist_ok=True)
        with open(wf, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return True, '已导入「%s」到 %s；重启实例后出现在项目列表里' % (title, dest_project)
    except Exception as exc:  # noqa: BLE001
        return False, '导入失败：%s' % exc
    finally:
        shutil.rmtree(work, ignore_errors=True)
