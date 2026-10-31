"""「更多」按钮改用设计稿的 i-more 图标（原来是 '⋯' 字形，偏大偏细）。

设计稿：`.btn-icon{38×38}` 内含 16px 的 i-more（三个实心圆点）。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

OLD = "        more.add(self._label('⋯', 'glyph'))"
NEW = "        more.add(self._icon('more', 'muted', 16))   # 设计稿 i-more（三个实心圆点）"


def main():
    s = io.open(GUI, encoding='utf-8').read()
    if NEW in s:
        print('already patched')
        return 0
    if OLD not in s:
        raise SystemExit('FAIL: 找不到更多按钮的字形')
    s = s.replace(OLD, NEW, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('more button -> i-more icon')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
