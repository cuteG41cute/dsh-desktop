#!/usr/bin/env python3
"""核对 GitHub Release（公开 API，无需 token），并可选校验附件哈希。

  python tools/host/verify-release.py v1.4.5 [本地 deb 路径]
"""
import hashlib
import io
import json
import sys
import urllib.request

REPO = 'cuteG41cute/dsh-desktop'


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else 'v1.4.5'
    local_deb = sys.argv[2] if len(sys.argv) > 2 else ''
    url = 'https://api.github.com/repos/%s/releases/tags/%s' % (REPO, tag)
    req = urllib.request.Request(url, headers={'User-Agent': 'dsh-release-check'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))

    print('release id : %s' % data['id'])
    print('tag        : %s' % data['tag_name'])
    print('draft      : %s | prerelease: %s' % (data['draft'], data['prerelease']))
    print('name       : %s' % data['name'])
    print('body       : %d chars' % len(data.get('body') or ''))
    print('page       : %s' % data['html_url'])
    assets = data.get('assets') or []
    print('assets     : %d' % len(assets))
    ok = True
    for a in assets:
        print('  - %-34s %10d bytes  state=%s' % (a['name'], a['size'], a['state']))
        print('    %s' % a['browser_download_url'])
        if local_deb and a['name'] == local_deb.split('/')[-1].split('\\')[-1]:
            local = hashlib.sha256(io.open(local_deb, 'rb').read()).hexdigest()
            print('    local  sha256: %s' % local)
            digest = a.get('digest') or ''
            if digest:
                print('    remote sha256: %s  %s' % (digest.split(':')[-1],
                                                     'MATCH' if digest.split(':')[-1] == local else 'MISMATCH'))
                ok = ok and digest.split(':')[-1] == local
            else:
                print('    remote 未提供 digest（GitHub 未返回），跳过哈希比对')
    print('\nRESULT: %s' % ('OK' if (assets and ok) else 'CHECK'))
    return 0 if assets and ok else 1


if __name__ == '__main__':
    sys.exit(main())
