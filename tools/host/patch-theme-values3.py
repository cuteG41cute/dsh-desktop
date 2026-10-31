"""Patch #3: 字号与日志表头按设计稿收口（生成的主题 CSS 会重新生成）。

对应 design/styles.css 里的：.log-header 45px、.log-title 12/650、.log-count 8、
.eyebrow 8/750/.16em、h1 25/680/-.035em、.page-heading p 11、.breadcrumb 11、
.status-badge 9/600、.metric-row span 8.5 / strong 12/650、.card-label 11/650。
"""
import io

P = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

TAIL = """
/* 日志表头 / 标题区 / 指标行：字号按设计稿收口 */
.log-header { min-height: 44px; padding: 0 18px; border-bottom: 1px solid $(inner-border); }
.log-title { font-size: 12px; font-weight: 650; }
.log-count { font-size: 8px; }
.eyebrow { font-size: 8px; font-weight: 750; letter-spacing: .16em; color: $(accent); }
.page-title { font-size: 25px; font-weight: 680; letter-spacing: -.035em; }
.page-sub { font-size: 11px; }
.breadcrumb { font-size: 11px; }
.status-badge { font-size: 9px; font-weight: 600; }
.metric-label { font-size: 8.5px; }
.metric-value { font-size: 12px; font-weight: 650; }
.card-label { font-size: 11px; font-weight: 650; }
.instance-item:selected, .instance-item.active { border-radius: 13px; }
.log-line { min-height: 27px; font-size: 8.5px; }
.log-level { font-size: 7.5px; padding: 2px 4px; }
"""


def main():
    s = io.open(P, encoding='utf-8').read()
    marker = '/* 日志表头 / 标题区 / 指标行：字号按设计稿收口 */'
    if marker in s:
        print('already patched')
        return 0
    s = s.rstrip('\n') + '\n' + TAIL
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('appended %d lines' % TAIL.count('\n'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
