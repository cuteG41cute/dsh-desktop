"""去掉 `.live-indicator` 上的旧内边距（设计稿里它没有 padding，只是 flex + 颜色）。"""
import io

CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

OLD = ".live-indicator { padding: 2px 7px; }"
NEW = ".live-indicator { padding: 0; font-size: 8.5px; }   /* 设计稿：无内边距，只有颜色 */"


def main():
    s = io.open(CSS, encoding='utf-8').read()
    if NEW in s:
        print('already patched')
        return 0
    if OLD not in s:
        raise SystemExit('FAIL: 找不到 .live-indicator 的内边距规则')
    s = s.replace(OLD, NEW, 1)
    io.open(CSS, 'w', encoding='utf-8', newline='\n').write(s)
    print('live-indicator padding cleared')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
