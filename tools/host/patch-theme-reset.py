"""Patch 10: 把 GTK 系统主题给按钮的默认底色/阴影全部清掉。

GTK 的 Breeze/Adwaita 会给每个 button 画一层底色和渐变。设计稿里
`.side-link` / `.new-instance` / `.instance-item` / `.text-btn` 都是**全透明**的
（只有 hover/选中态有底），所以亮色主题下偏差小、暗色主题下整体偏亮
（实测 alpine-night 侧栏 +14 个色阶，正是这个原因）。

这段放在模板最前面，后面的具体规则照常覆盖它。
"""
import io

CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

BLOCK = """/* ---------- 系统主题重置 ----------
 * GTK 的默认主题会给 button 画底色/渐变/内阴影；设计稿只有 hover 与选中态才有底色。
 * 不重置的话，暗色主题整片偏亮（实测 alpine-night 侧栏 +14 色阶）。 */
button {
  background-image: none;
  border-image: none;
  box-shadow: none;
  text-shadow: none;
}
.side-link,
.new-instance,
.instance-item,
.text-btn,
.log-view,
.row-flat {
  background-color: transparent;
  box-shadow: none;
}
.side-link.selected,
.side-link:selected,
.instance-item:selected,
.instance-item.active {
  background-color: $(hover);
}

"""

MARKER = '/* 系统主题重置 */'


def main():
    s = io.open(CSS, encoding='utf-8').read()
    if MARKER in s:
        print('already patched')
        return 0
    # 插到模板注释结束之后、第一条真实规则之前
    anchor = '/* ---------- 动效 ----------'
    if anchor not in s:
        raise SystemExit('FAIL: 找不到动效注释锚点')
    s = s.replace(anchor, BLOCK + anchor, 1)
    io.open(CSS, 'w', encoding='utf-8', newline='\n').write(s)
    print('inserted system-theme reset block')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
