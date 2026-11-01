"""去掉 GTK 自己画的 CSD 装饰（那条 6px 深色边就是它）。

现象：窗口四周有一圈约 6px 的灰蓝渐变边，圆角处更明显，看起来像"两层圆角"。

实测像素（vm-shots/manager-dpms.png）：
  顶部 x=600     y=0..5  RGB 176→153（灰蓝渐变），y=6 起才是界面（252）
  右侧 y=300     x≤1249 界面，x=1250 起 140→187（同样的灰蓝）
说明窗口内缘被画了一圈装饰阴影/边框。

原因：我们用的是 CSD（self.set_titlebar(零高度控件)），GTK 会给窗口画主题的
`decoration` 节点（含 box-shadow / border / margin）。我们的自绘背景画在它下面，
于是这圈阴影盖在界面边缘上。

修法：把 `decoration` 节点的阴影、边框、外边距全部清掉 —— 阴影和圆角都由我们
自己的 draw 处理器负责。
"""
import io

CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

TAIL = """
/* GTK 的 CSD 装饰节点：阴影/边框/外边距全部清零。
   我们自己在 draw 里画圆角与背景（含阴影），GTK 再画一圈就会变成"双层边"。 */
decoration {
  box-shadow: none;
  border: none;
  margin: 0;
  padding: 0;
  background-color: transparent;
  border-radius: 0;
}
decoration:backdrop { box-shadow: none; border: none; }
"""


def main():
    s = io.open(CSS, encoding='utf-8').read()
    if 'decoration:backdrop' in s:
        print('already patched')
        return 0
    io.open(CSS, 'w', encoding='utf-8', newline='\n').write(s.rstrip('\n') + '\n' + TAIL)
    print('CSD decoration styling cleared')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
