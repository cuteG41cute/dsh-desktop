# -*- coding: utf-8 -*-
"""项目目录 / 备份记录 / 备份计划（Linux 端，与 Windows ProjectCatalog 对齐）。"""
import json
import os
import shutil
import time
import uuid
from datetime import datetime, timedelta

from . import project_migration as mig


def manager_dir():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'dsh-manager')


def backups_file():
    return os.path.join(manager_dir(), 'backups.json')


def plan_file():
    return os.path.join(manager_dir(), 'backup-plan.json')


def instance_home(instance_dir):
    """实例的 DSH 数据根：<Dir>/dsh-home 优先，否则 ~/.dsh。"""
    per = os.path.join(instance_dir or '', 'dsh-home')
    if instance_dir and os.path.isdir(per):
        return per
    return os.environ.get('DSH_HOME') or os.path.expanduser('~/.dsh')


SKIP = {'node_modules', '.git', '.vs', 'bin', 'obj', 'dist', '.dsh-backup', '.tmp'}


def _measure(project_path, session_dir):
    last = None
    size = 0

    def walk(root):
        nonlocal last, size
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for name in files:
                full = os.path.join(base, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                size += st.st_size
                t = datetime.fromtimestamp(st.st_mtime)
                if last is None or t > last:
                    last = t

    if os.path.isdir(project_path):
        walk(project_path)
    if os.path.isdir(session_dir):
        try:
            for base, dirs, files in os.walk(session_dir):
                for name in files:
                    full = os.path.join(base, name)
                    st = os.stat(full)
                    size += st.st_size
                    t = datetime.fromtimestamp(st.st_mtime)
                    if last is None or t > last:
                        last = t
        except OSError:
            pass
    return last, size


def _handoff(project_path):
    d = os.path.join(project_path, '.dsh', 'handoff')
    if not os.path.isdir(d):
        return None
    files = [f for f in os.listdir(d) if f.endswith('.json') and not f.startswith('.')]
    if not files:
        return None
    files.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
    try:
        with open(os.path.join(d, files[0]), encoding='utf-8') as fh:
            data = json.load(fh)
        return {
            'device': data.get('deviceShort') or data.get('deviceId') or '另一台设备',
            'at': data.get('exportedAt') or '',
            'title': data.get('title') or '',
            'summary': data.get('summary') or '',
            'record': data.get('fullPath') or files[0],
        }
    except (OSError, ValueError):
        return None


def list_backups():
    try:
        with open(backups_file(), encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_backups(records):
    os.makedirs(manager_dir(), exist_ok=True)
    with open(backups_file(), 'w', encoding='utf-8') as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)


def list_projects(home):
    """返回实例下的项目列表（含会话数、体积、活动、备份状态）。"""
    ws_file = os.path.join(home, 'storages', 'workspace.json')
    if not os.path.isfile(ws_file):
        return []
    try:
        with open(ws_file, encoding='utf-8') as fh:
            data = json.load(fh)
        workspaces = (data.get('tables') or {}).get('workspaces') or {}
    except (OSError, ValueError):
        return []

    backups = list_backups()
    out = []
    for wid, item in workspaces.items():
        path = item.get('path') or ''
        title = item.get('title') or os.path.basename(path)
        session_ids = item.get('sessionIds') or []
        session_dir = os.path.join(home, 'sessions', mig.project_key(path))
        sessions = len(session_ids)
        if os.path.isdir(session_dir):
            on_disk = len([d for d in os.listdir(session_dir)
                           if os.path.isdir(os.path.join(session_dir, d))])
            sessions = max(sessions, on_disk)
        last, size = _measure(path, session_dir)
        recs = [b for b in backups
                if (b.get('projectPath') or '').lower() == path.lower()
                or b.get('projectId') == wid]
        recs.sort(key=lambda b: b.get('createdAt') or '', reverse=True)
        state, last_at, location = 'none', None, ''
        if recs:
            last_at = recs[0].get('createdAt') or ''
            location = recs[0].get('kind') or 'local'
            if last and last_at and last > datetime.fromisoformat(last_at.replace('Z', '+00:00')).replace(tzinfo=None):
                state = 'outdated'
            else:
                state = 'backup'
        out.append({
            'id': wid, 'path': path, 'title': title, 'sessions': sessions,
            'size': size, 'last_activity': last.isoformat() if last else '',
            'backup_state': state, 'last_backup_at': last_at,
            'backup_location': location, 'has_handoff': _handoff(path) is not None,
        })
    out.sort(key=lambda p: p['last_activity'] or '', reverse=True)
    return out


def load_plan(instance_id):
    try:
        with open(plan_file(), encoding='utf-8') as fh:
            data = json.load(fh)
        return data.get(instance_id) or {}
    except (OSError, ValueError):
        return {}


def save_plan(instance_id, plan):
    os.makedirs(manager_dir(), exist_ok=True)
    try:
        with open(plan_file(), encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data[instance_id] = plan
    with open(plan_file(), 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def apply_retention(project_dir, keep_count, keep_days):
    try:
        files = [os.path.join(project_dir, f) for f in os.listdir(project_dir) if f.endswith('.dshproj')]
    except OSError:
        return
    files.sort(key=os.path.getmtime, reverse=True)
    keep = max(1, int(keep_count or 1))
    for i, f in enumerate(files):
        expired = i >= keep
        if keep_days and os.path.getmtime(f) < time.time() - keep_days * 86400:
            expired = True
        if expired:
            try:
                os.remove(f)
            except OSError:
                pass


def run_backup(instance_id, home, projects, plan, log=None):
    target_dir = plan.get('directory') or os.path.join(os.path.expanduser('~'), 'dsh-backup')
    os.makedirs(target_dir, exist_ok=True)
    records = list_backups()
    ok = failed = 0
    keep = int(plan.get('retentionCount') or 1)
    for p in projects:
        name = mig_safe(p['title'])
        folder = os.path.join(target_dir, name) if keep > 1 else target_dir
        os.makedirs(folder, exist_ok=True)
        if keep > 1:
            fname = '%s-%s.dshproj' % (name, time.strftime('%Y%m%d-%H%M%S'))
        else:
            fname = name + '.dshproj'
        bundle = os.path.join(folder, fname)
        success, msg = mig.export(
            {'id': p['id'], 'path': p['path'], 'title': p['title'], 'sessions': p['sessions']},
            bundle, include_files=bool(plan.get('includeProjectFiles', True)), log=log)
        if success:
            ok += 1
            records = [r for r in records
                       if not ((r.get('projectPath') or '').lower() == p['path'].lower()
                               and r.get('kind') == 'local')]
            records.append({
                'projectId': p['id'], 'projectTitle': p['title'], 'projectPath': p['path'],
                'kind': 'local', 'file': bundle,
                'deviceShort': 'linux-' + os.uname().nodename if hasattr(os, 'uname') else 'linux',
                'createdAt': datetime.now().isoformat(),
                'sizeBytes': os.path.getsize(bundle), 'sha256': '', 'status': 'ok',
            })
            if keep > 1:
                apply_retention(folder, keep, int(plan.get('retentionDays') or 0))
        else:
            failed += 1
            if log:
                log('%s: %s' % (p['title'], msg))
    save_backups(records)
    return ok, failed


def mig_safe(name):
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, '_')
    return name
