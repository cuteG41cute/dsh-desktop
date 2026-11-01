"""发现结果里保留内置目录的"提示"：subdir / 显示名 / 插件 id。

问题：`dsh-mobile` 仓库里的插件其实在 `netmon/` 子目录（内置目录里叫 dsh-netmon）。
只按仓库名做条目，安装时可能挑错包，列表里也会出现两个名字。

做法：按仓库全名建一张提示表（来自 CATALOG 里 repo 非空的条目），
发现到的仓库若命中，就沿用它的 subdir / id / 名称。
"""
import io

P = 'dsh-desktop/linux/manager/dsh_manager/plugins.py'

OLD = """def _entry_from_repo(repo):
    \"\"\"GitHub 仓库对象 → 插件条目（字段与 CATALOG 对齐）。\"\"\"
    name = repo.get('name') or ''
    return {
        'id': name,
        'name': name,
        'repo': repo.get('full_name') or '',
        'subdir': '',                      # 让它按"含 package.json 的目录"自动挑包
        'desc': (repo.get('description') or '').strip(),
        'inject': [],
        'stars': repo.get('stargazers_count') or 0,
        'updated': (repo.get('pushed_at') or '')[:10],
        'url': repo.get('html_url') or '',
        'discovered': True,
    }"""

NEW = """def _hints():
    \"\"\"仓库全名 → 内置目录里的提示（subdir / id / 显示名）。

    有些仓库的插件在子目录里（dsh-mobile 的 netmon/），只按仓库名做条目会挑错包。
    \"\"\"
    out = {}
    for item in CATALOG:
        repo = (item.get('repo') or '').strip()
        if repo:
            out[repo.lower()] = item
    return out


def _entry_from_repo(repo, hints=None):
    \"\"\"GitHub 仓库对象 → 插件条目（字段与 CATALOG 对齐，命中提示时沿用内置值）。\"\"\"
    full = repo.get('full_name') or ''
    name = repo.get('name') or ''
    hint = (hints or {}).get(full.lower()) or {}
    return {
        'id': hint.get('id') or name,
        'name': hint.get('name') or name,
        'repo': full,
        'subdir': hint.get('subdir') or '',   # 没提示就按"含 package.json 的目录"自动挑包
        'desc': (repo.get('description') or '').strip(),
        'inject': hint.get('inject') or [],
        'stars': repo.get('stargazers_count') or 0,
        'updated': (repo.get('pushed_at') or '')[:10],
        'url': repo.get('html_url') or '',
        'discovered': True,
    }"""

OLD2 = """    out = []
    for repo in data:
        topics = [str(t).lower() for t in (repo.get('topics') or [])]
        if topic not in topics:
            continue
        out.append(_entry_from_repo(repo))"""
NEW2 = """    hints = _hints()
    out = []
    for repo in data:
        topics = [str(t).lower() for t in (repo.get('topics') or [])]
        if topic not in topics:
            continue
        out.append(_entry_from_repo(repo, hints))"""


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in ((OLD, NEW), (OLD2, NEW2)):
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0 if not missing else 1


if __name__ == '__main__':
    raise SystemExit(main())
