#!/usr/bin/env python3
"""生成任一版本的 GitHub Release 载荷（UTF-8 无 BOM）。

  python tools/host/make-release-payload.py v1.4.8 recovery/RELEASE-NOTES-v1.4.8.md "标题"

中文只从文件/参数读入文件后再交给 gh，避免 PowerShell 5.1 把中文参数按 ANSI 传坏。
"""
import io
import json
import os
import sys


def main():
    if len(sys.argv) < 4:
        raise SystemExit('usage: make-release-payload.py TAG NOTES_MD "TITLE"')
    tag, notes, title = sys.argv[1], sys.argv[2], sys.argv[3]
    with io.open(notes, encoding='utf-8') as fh:
        body = fh.read()
    out = os.path.join(os.environ.get('TEMP', '/tmp'), 'release-%s.json' % tag)
    payload = {'tag_name': tag, 'name': title, 'body': body, 'draft': False, 'prerelease': False}
    with io.open(out, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print('payload -> %s (%d chars body)' % (out, len(body)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
