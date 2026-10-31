"""焦点环改用 box-shadow 实现。

GTK3 的 `outline` 会参与尺寸计算：实测加上 3px outline 后所有按钮变高、整页位移，
宽屏像素 MAE 从 3.81 涨到 5.24。box-shadow 不参与布局，视觉上等价。
"""
import io

CSS = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

OLD = """button:focus, .btn:focus, .side-link:focus, .instance-item:focus,
.quick-action:focus, .icon-btn:focus, entry:focus, spinbutton:focus {
  outline: 3px solid alpha($(accent), .25);
  outline-offset: 2px;
}"""

NEW = """button:focus, .btn:focus, .side-link:focus, .instance-item:focus,
.quick-action:focus, .icon-btn:focus {
  /* box-shadow 不参与布局；GTK3 的 outline 会计入尺寸（实测整页位移、
     宽屏 MAE 3.81→5.24），所以焦点环用阴影画。 */
  box-shadow: 0 0 0 3px alpha($(accent), .25);
}
entry:focus, spinbutton:focus {
  box-shadow: 0 0 0 3px alpha($(accent), .25);
  border-color: alpha($(accent), .5);
}"""


def main():
    s = io.open(CSS, encoding='utf-8').read()
    if 'box-shadow: 0 0 0 3px alpha($(accent), .25)' in s and 'outline: 3px solid' not in s:
        print('already patched')
        return 0
    if OLD not in s:
        raise SystemExit('FAIL: 找不到焦点环样式块')
    s = s.replace(OLD, NEW, 1)
    io.open(CSS, 'w', encoding='utf-8', newline='\n').write(s)
    print('focus ring -> box-shadow')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
