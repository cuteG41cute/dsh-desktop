"""Patch 12: 侧栏标题/实例列表/运行环境卡/日志卡的盒模型对齐。

发现的三处（都是"GTK min-height 是内容盒"和"卡片 padding 不应作用于子区块"）：

1. `.runtime` 的 min-height 54 + padding 26 + border 2 = 82（设计稿 56）→ 改成 28。
2. 日志卡是 `.card`，但设计稿 `.log-card` 没有内边距（表头直接贴边）→ padding: 0。
3. 侧栏"我的实例"标题：设计稿是容器 padding 0 8px，GTK 用了 margin → 盒宽 199 而非 215。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

GUI_SUBS = [
    ("        head.set_margin_start(8)\n        head.set_margin_end(8)\n"
     "        head.set_margin_bottom(7)",
     "        head.set_margin_bottom(7)   # 左右留白交给 CSS 的 padding（设计稿 .side-section-title）"),
    # 最后一行不要额外底边距（设计稿 3×61 + 2×5 = 193）
    ("        self.instance_list.show_all()",
     "        last = self._list_rows()\n"
     "        if last:\n"
     "            last[-1].set_margin_bottom(0)\n"
     "        self.instance_list.show_all()"),
]

CSS_TAIL = """
/* 盒模型收口（GTK 的 min-height 只算内容盒） */
.runtime { min-height: 28px; padding: 13px 10px; }
.log-card { padding: 0; }
.side-section-title { padding: 0 8px; }
"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in GUI_SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:70])
            continue
        s = s.replace(old, new, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)

    c = io.open(CSS, encoding='utf-8').read()
    marker = '/* 盒模型收口（GTK 的 min-height 只算内容盒） */'
    if marker not in c:
        io.open(CSS, 'w', encoding='utf-8', newline='\n').write(c.rstrip('\n') + '\n' + CSS_TAIL)
    print('gui patched, missing: %s' % (missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
