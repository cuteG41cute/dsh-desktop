"""给 MainWindow 加响应式布局（窄屏/矮屏自适应），支持缩到 1/4 屏（720×450）。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')

ANCHOR = '''        SizeChanged += (_, _) => UpdateShellClip();'''

NEW_ANCHOR = '''        SizeChanged += (_, _) =>
        {
            UpdateShellClip();
            ApplyResponsive();
        };'''

RESPONSIVE = '''
    /// <summary>
    /// 响应式布局：窗口可以缩到 1/4 屏（720×450）。
    ///  - 宽度 &lt; 1060：实例卡/快捷控制卡上下堆叠（侧栏也收窄）
    ///  - 宽度 &lt; 900：侧栏 180，内容边距收紧
    ///  - 高度 &lt; 620：隐藏页头描述与页脚
    ///  - 常用功能按可用宽度自动 4/3/2 列
    /// </summary>
    private void ApplyResponsive()
    {
        if (Quick1 == null || OverviewGrid == null) return;
        var w = ActualWidth;
        var h = ActualHeight;
        var narrow = w < 1060;
        var tight = w < 900;
        var shortH = h < 620;

        try
        {
            SidebarCol.Width = new GridLength(tight ? 180 : (narrow ? 220 : 248));
            ContentScroll.Padding = tight ? new Thickness(18, 16, 18, 12)
                                          : new Thickness(30, 25, 30, 15);
            PageDesc.Visibility = shortH ? Visibility.Collapsed : Visibility.Visible;
            PageFooter.Visibility = shortH ? Visibility.Collapsed : Visibility.Visible;

            // 概览两卡：窄屏上下堆叠
            if (narrow)
            {
                OverviewGrid.ColumnDefinitions.Clear();
                OverviewGrid.ColumnDefinitions.Add(new ColumnDefinition());
                if (OverviewGrid.RowDefinitions.Count == 0)
                {
                    OverviewGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    OverviewGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                }
                Grid.SetColumn(InstanceCard, 0);
                Grid.SetColumnSpan(InstanceCard, 1);
                Grid.SetRow(InstanceCard, 0);
                Grid.SetColumn(ControlCard, 0);
                Grid.SetColumnSpan(ControlCard, 1);
                Grid.SetRow(ControlCard, 1);
                ControlCard.Margin = new Thickness(0, 14, 0, 0);
            }
            else
            {
                OverviewGrid.RowDefinitions.Clear();
                OverviewGrid.ColumnDefinitions.Clear();
                OverviewGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1.65, GridUnitType.Star) });
                OverviewGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(16) });
                OverviewGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                Grid.SetRow(InstanceCard, 0);
                Grid.SetRow(ControlCard, 0);
                Grid.SetColumn(InstanceCard, 0);
                Grid.SetColumn(ControlCard, 2);
                Grid.SetColumnSpan(InstanceCard, 1);
                Grid.SetColumnSpan(ControlCard, 1);
                ControlCard.Margin = new Thickness(0);
            }

            // 常用功能：按可用宽度决定列数，WrapPanel 自动换行
            var side = tight ? 180 : (narrow ? 220 : 248);
            var pad = tight ? 36 : 60;
            var avail = Math.Max(300, w - side - pad);
            var cols = avail >= 900 ? 4 : (avail >= 620 ? 3 : 2);
            var gap = 11.0;
            var cardW = Math.Max(150, Math.Floor((avail - gap * (cols - 1)) / cols));
            var cards = new[] { Quick1, Quick2, Quick3, Quick4 };
            for (var i = 0; i < cards.Length; i++)
            {
                cards[i].Width = cardW;
                cards[i].Margin = new Thickness(0, 0, (i % cols == cols - 1) ? 0 : gap, gap);
            }
        }
        catch { }
    }
'''

FIELDS_END = '''    private double Dpi => VisualTreeHelper.GetDpi(this).DpiScaleX;'''

FIELDS_NEW = '''    private double Dpi => VisualTreeHelper.GetDpi(this).DpiScaleX;

    private void OnLoadedResponsive(object sender, RoutedEventArgs e) => ApplyResponsive();'''


def main():
    src = io.open(P, encoding='utf-8').read()
    if ANCHOR not in src:
        print('MISS anchor')
        return 1
    src = src.replace(ANCHOR, NEW_ANCHOR, 1)
    if FIELDS_END not in src:
        print('MISS fields')
        return 1
    src = src.replace(FIELDS_END, FIELDS_NEW, 1)
    anchor2 = '    private void OnLoaded(object sender, RoutedEventArgs e)\n    {'
    if anchor2 not in src:
        print('MISS onloaded')
        return 1
    src = src.replace(anchor2, RESPONSIVE + '\n' + anchor2, 1)
    # OnLoaded 末尾调用一次
    tail = '        FooterPath.Text = "实例根目录 · " + RootDir;\n    }'
    if tail not in src:
        print('MISS onloaded tail')
        return 1
    src = src.replace(tail, '        FooterPath.Text = "实例根目录 · " + RootDir;\n        ApplyResponsive();\n    }', 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('responsive added')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
