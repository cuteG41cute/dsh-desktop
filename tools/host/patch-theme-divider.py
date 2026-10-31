"""Patch 9: 顶栏分隔线 + 通知小圆点的样式（对应设计稿 .top-divider / .notification-dot）。"""
import io

CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

TAIL = """
/* 顶栏分隔线（设计稿 .top-divider：1×20 的 inner-border） */
.top-divider { background-color: $(inner-border); min-width: 1px; min-height: 20px; }
"""


def main():
    s = io.open(CSS, encoding='utf-8').read()
    if '.top-divider' in s:
        print('already patched')
        return 0
    io.open(CSS, 'w', encoding='utf-8', newline='\n').write(s.rstrip('\n') + '\n' + TAIL)
    print('appended divider/dot styles')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
