"""生成 GitHub Release 的 API 载荷（UTF-8 无 BOM）。

为什么不直接把标题写在命令行里：PowerShell 5.1 会把中文参数按 ANSI 传出去，
gh/curl 收到就是乱码（之前发 dsh-screenshot 时踩过）。所以中文一律走文件。
"""
import io
import json
import os
import sys

NOTES = 'recovery/RELEASE-NOTES-v1.4.5.md'
OUT = os.path.join(os.environ.get('TEMP', '/tmp'), 'release-1.4.5.json')
TAG = 'v1.4.5'
NAME = 'dsh-manager 1.4.5 — 按设计规范逐像素复刻'


def main():
    with io.open(NOTES, encoding='utf-8') as fh:
        body = fh.read()
    payload = {
        'tag_name': TAG,
        'name': NAME,
        'body': body,
        'draft': False,
        'prerelease': False,
    }
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print('payload -> %s (%d chars, name=%r)' % (OUT, len(body), NAME))
    return 0


if __name__ == '__main__':
    sys.exit(main())
