"""插件列表改成"从 GitHub 账户发现"：只显示带 dsh-plugin topic 的仓库。

用户要求：不再用写死的 CATALOG，而是探测他的 GitHub 账户里所有打了 `dsh-plugin`
标签的仓库，把结果作为插件目录（装了哪个、版本多少仍然照旧检测）。

实现：
· `github_plugins()` 拉 `GET /users/<user>/repos`（实测该域名在虚拟机里通，200），
  按 `topics` 过滤 `dsh-plugin`；
· 结果缓存到 `~/.cache/dsh-manager/plugin-cache/github-plugins.json`（带时间戳），
  离线时用缓存；
· `catalog()` / `find()` / `all_entries()` 全部改为"有发现结果就用它，否则退回内置 CATALOG"，
  这样断网、没打标签时功能不退化。
"""
import io

P = 'dsh-desktop/linux/manager/dsh_manager/plugins.py'

SUB_CATALOG = ("def catalog():\n"
               "    return [dict(item) for item in CATALOG]")
NEW_CATALOG = ("def catalog():\n"
               "    \"\"\"当前插件目录：优先 GitHub 发现结果（带 dsh-plugin 标签的仓库），\n"
               "    没有就退回内置 CATALOG。\"\"\"\n"
               "    if _DYNAMIC:\n"
               "        return [dict(item) for item in _DYNAMIC]\n"
               "    return [dict(item) for item in CATALOG]")

SUB_FIND = "def find(id_):\n    for item in CATALOG:"
NEW_FIND = "def find(id_):\n    for item in catalog():"

SUB_KNOWN = "    known = {item['id'] for item in CATALOG}"
NEW_KNOWN = "    known = {item['id'] for item in catalog()}"

TAIL = '''

# ---------------------------------------------------------------------------
# GitHub 插件发现（topic: dsh-plugin）
# ---------------------------------------------------------------------------
GH_USER = 'cuteG41cute'
GH_TOPIC = 'dsh-plugin'
_DYNAMIC = []          # 发现到的插件条目（空 = 用内置 CATALOG）


def github_cache_path():
    return os.path.join(cache_dir(), 'github-plugins.json')


def _entry_from_repo(repo):
    """GitHub 仓库对象 → 插件条目（字段与 CATALOG 对齐）。"""
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
    }


def github_plugins(user=None, topic=None, timeout=15):
    """列出某账号下打了 topic 标签的仓库（公开 API，无需 token）。"""
    user = user or GH_USER
    topic = (topic or GH_TOPIC).lower()
    url = 'https://api.github.com/users/%s/repos?per_page=100&sort=updated' % user
    req = urllib.request.Request(url, headers=dict(UA, Accept='application/vnd.github+json'))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    out = []
    for repo in data:
        topics = [str(t).lower() for t in (repo.get('topics') or [])]
        if topic not in topics:
            continue
        out.append(_entry_from_repo(repo))
    out.sort(key=lambda e: e['id'])
    return out


def load_github_cache():
    """读缓存；返回 (items, fetched_iso) 或 ([], '')。"""
    try:
        with open(github_cache_path(), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return list(data.get('items') or []), data.get('fetched') or ''
    except (OSError, ValueError):
        return [], ''


def save_github_cache(items):
    os.makedirs(cache_dir(), exist_ok=True)
    payload = {'fetched': time.strftime('%Y-%m-%d %H:%M:%S'), 'user': GH_USER,
               'topic': GH_TOPIC, 'items': items}
    tmp = github_cache_path() + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, github_cache_path())
    return payload['fetched']


def bootstrap_cache():
    """启动/开对话框时先用缓存，避免列表一闪变成空的。"""
    global _DYNAMIC
    items, fetched = load_github_cache()
    if items:
        _DYNAMIC = items
    return items, fetched


def refresh_github(user=None, topic=None, timeout=15):
    """真正联网刷新一次，成功则替换目录并写缓存。"""
    global _DYNAMIC
    items = github_plugins(user=user, topic=topic, timeout=timeout)
    _DYNAMIC = items
    fetched = save_github_cache(items)
    return items, fetched


def source_info():
    """给界面显示"这批列表是从哪来的"。"""
    items, fetched = load_github_cache()
    if _DYNAMIC:
        return ('GitHub · %s（topic: %s）' % (GH_USER, GH_TOPIC),
                fetched or '（本次会话内刷新）')
    return ('内置目录（GitHub 上还没有带 dsh-plugin 标签的仓库）', '')
'''


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in ((SUB_CATALOG, NEW_CATALOG), (SUB_FIND, NEW_FIND), (SUB_KNOWN, NEW_KNOWN)):
        if old not in s:
            missing.append(old.split('\n')[0][:50])
            continue
        s = s.replace(old, new, 1)
    if 'def github_plugins' not in s:
        s = s.rstrip('\n') + '\n' + TAIL
    if 'import time' not in s.split('def ')[0]:
        s = s.replace('import tempfile\n', 'import tempfile\nimport time\n', 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('plugins.py patched, missing: %s' % (missing if missing else 'none'))
    return 0 if not missing else 1


if __name__ == '__main__':
    raise SystemExit(main())
