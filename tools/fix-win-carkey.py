"""一次性修补：把 Common.xaml 里的 Card 样式改名 CardStyle（避免和主题里的 Card 画刷撞 key）。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    full = os.path.join(ROOT, path)
    src = io.open(full, encoding='utf-8').read()
    total = 0
    for old, new in pairs:
        n = src.count(old)
        total += n
        src = src.replace(old, new)
    io.open(full, 'w', encoding='utf-8', newline='\n').write(src)
    print('%s: %d 处' % (path, total))


patch('dsh-manager-win/Styles/Common.xaml', [
    ('x:Key="Card" TargetType="Border"', 'x:Key="CardStyle" TargetType="Border"'),
])
patch('dsh-manager-win/MainWindow.xaml', [
    ('{StaticResource Card}', '{StaticResource CardStyle}'),
])
