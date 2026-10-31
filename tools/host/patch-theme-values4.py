"""Patch 4: 卡片高度与常用功能区的垂直节奏，按设计稿落。

设计稿：.instance-card/.control-card min-height 205；.quick-section margin-top 21；
.section-heading margin-bottom 11；.quick-grid gap 11；.log-card margin-top 20。
GTK 的 min-height 是内容盒 → 205 - 2(border) = 203。
"""
import io

P = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

TAIL = """
/* 卡片与分区节奏：数值取自 design/styles.css */
.instance-card, .control-card { min-height: 203px; }
.quick-section { margin-top: 21px; }
.section-heading { margin-bottom: 11px; }
.log-card { margin-top: 20px; }
.overview-grid { column-spacing: 16px; row-spacing: 16px; }
.page-heading { margin-bottom: 22px; }
"""


def main():
    s = io.open(P, encoding='utf-8').read()
    marker = '/* 卡片与分区节奏：数值取自 design/styles.css */'
    if marker in s:
        print('already patched')
        return 0
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s.rstrip('\n') + '\n' + TAIL)
    print('appended')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
