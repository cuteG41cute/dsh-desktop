"""给窗口设置应用图标，验证右上角那个蓝色方块是不是"窗口图标"。

现象：无边框 + 非最大化时，关闭按钮附近会多出一个带白色雪花/齿轮的蓝色方块；
最大化时却没有。怀疑是 KWin 在给"没有服务端装饰"的窗口画应用图标兜底。
显式设置窗口图标后：如果是它，方块会变成我们的图标（鲸鱼）；如果没变，那就是别的东西。
顺带这也让任务栏/切换器里显示正确图标。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

OLD = """        self.set_decorated(False)
        # 关键：给一个零高度的自绘标题栏"""
NEW = """        self.set_decorated(False)
        # 窗口图标：任务栏/切换器用得到；也顺便观察它是不是右上角那个方块
        for icon_path in (os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                                      'share', 'dsh-desktop.png'),
                          '/usr/lib/dsh-manager/share/dsh-desktop.png',
                          '/usr/share/icons/hicolor/256x256/apps/dsh-manager.png'):
            try:
                if os.path.exists(icon_path):
                    self.set_icon_from_file(icon_path)
                    break
            except Exception:
                continue
        # 关键：给一个零高度的自绘标题栏"""


def main():
    s = io.open(GUI, encoding='utf-8').read()
    if 'set_icon_from_file' in s:
        print('already patched')
        return 0
    if OLD not in s:
        raise SystemExit('FAIL: anchor missing')
    s = s.replace(OLD, NEW, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('window icon set explicitly')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
