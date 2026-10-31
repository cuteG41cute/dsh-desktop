"""计数胶囊再矮一点：CHIP_PAD('count-pill') 1px → 0px，配合 min-height 12 更接近设计稿的 20×14。"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

OLD = "        'badge': (4, 9), 'subtle-tag': (3, 7), 'count-pill': (1, 6),"
NEW = "        'badge': (4, 9), 'subtle-tag': (3, 7), 'count-pill': (0, 6),"


def main():
    s = io.open(GUI, encoding='utf-8').read()
    if NEW in s:
        print('already patched')
        return 0
    if OLD not in s:
        raise SystemExit('FAIL: 找不到 CHIP_PAD 定义')
    s = s.replace(OLD, NEW, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('count-pill pad -> (0, 6)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
