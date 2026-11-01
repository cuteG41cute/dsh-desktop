"""接上「更多」菜单：查看 Token / 重建窗口 / 在文件管理器中显示 / 检查更新 / 修复 / 卸载。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')

CODE = '''
    // ---------------------------------------------------------------- 更多菜单
    private void ShowMoreMenu()
    {
        if (_current == null) return;
        var panel = new StackPanel { Margin = new Thickness(6) };
        void Item(string text, string iconKey, Action act, Brush fg = null)
        {
            var grid = new Grid { Height = 34 };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(26) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var icon = new Path
            {
                Data = TryFindResource(iconKey) as Geometry,
                Stretch = Stretch.Uniform, Width = 15, Height = 15,
                VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(10, 0, 0, 0),
                Stroke = fg ?? (Brush)(TryFindResource("Muted") ?? Brushes.Gray),
                StrokeThickness = 1.7, Fill = null,
            };
            var label = new TextBlock
            {
                Text = text, FontSize = 10.5, VerticalAlignment = VerticalAlignment.Center,
                Foreground = fg ?? (Brush)(TryFindResource("Text") ?? Brushes.Black),
            };
            Grid.SetColumn(icon, 0);
            Grid.SetColumn(label, 1);
            grid.Children.Add(icon);
            grid.Children.Add(label);
            var btn = new Button
            {
                Content = grid, Background = Brushes.Transparent, BorderThickness = new Thickness(0),
                Cursor = Cursors.Hand, HorizontalContentAlignment = HorizontalAlignment.Stretch,
            };
            btn.Template = RowTemplate();
            btn.Click += (_, _) => { _morePopup.IsOpen = false; act(); };
            panel.Children.Add(btn);
        }

        Item("查看 Token", "Icon.key", OnShowToken);
        Item("重建窗口", "Icon.restart", OnRebuildWindow);
        Item("在文件管理器中显示", "Icon.folder",
            () => DshHost.OpenFolder(System.IO.Path.GetDirectoryName(_current.Entry) ?? ""));
        panel.Children.Add(new Border { Height = 1, Margin = new Thickness(6, 5, 6, 5),
            Background = (Brush)(TryFindResource("InnerBorder") ?? Brushes.Gainsboro) });
        Item("检查更新", "Icon.update", () => _ = CheckUpdateAsync());
        Item("修复实例", "Icon.wrench", () => _ = RepairAsync());
        var danger = (Brush)(TryFindResource("Danger") ?? Brushes.IndianRed);
        Item("卸载实例", "Icon.trash", OnUninstallInstance, danger);

        var card = new Border
        {
            Width = 215, Padding = new Thickness(6), CornerRadius = new CornerRadius(14),
            Background = (Brush)(TryFindResource("CardSolid") ?? Brushes.White),
            BorderBrush = (Brush)(TryFindResource("Border") ?? Brushes.Gainsboro),
            BorderThickness = new Thickness(1), Child = panel,
            Effect = new System.Windows.Media.Effects.DropShadowEffect
            { BlurRadius = 40, ShadowDepth = 16, Direction = 270, Opacity = 0.18, Color = Colors.Black },
        };
        _morePopup = new Popup
        {
            PlacementTarget = MoreBtn, Placement = PlacementMode.Bottom, StaysOpen = false,
            AllowsTransparency = true, VerticalOffset = 6, HorizontalOffset = -160, Child = card,
        };
        _morePopup.IsOpen = true;
    }

    private static ControlTemplate RowTemplate()
    {
        var tmpl = new ControlTemplate(typeof(Button));
        var bd = new FrameworkElementFactory(typeof(Border));
        bd.SetValue(Border.CornerRadiusProperty, new CornerRadius(8));
        bd.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Button.BackgroundProperty));
        var cp = new FrameworkElementFactory(typeof(ContentPresenter));
        cp.SetValue(HorizontalAlignmentProperty, HorizontalAlignment.Stretch);
        bd.AppendChild(cp);
        tmpl.VisualTree = bd;
        return tmpl;
    }

    private void OnShowToken()
    {
        if (_current == null) return;
        var url = "http://127.0.0.1:" + _current.Port + "/";
        try
        {
            Clipboard.SetText(url);
            Toast("访问地址已复制：" + url);
        }
        catch { Toast("复制失败（剪贴板被占用）"); }
    }

    private void OnRebuildWindow()
    {
        if (_current == null) return;
        DshHost.Stop(_current, out _);
        DshHost.Start(_current, out var msg);
        PollCurrent();
        Toast(msg);
    }

    private async System.Threading.Tasks.Task CheckUpdateAsync()
    {
        if (_current == null) return;
        Toast("正在检查更新…");
        var (ok, msg) = await InstanceActions.UpdateAsync(_current, l => Diag(l));
        if (ok)
        {
            ReloadInstances();
            Toast(msg);
        }
        else Toast(msg);
    }

    private async System.Threading.Tasks.Task RepairAsync()
    {
        if (_current == null) return;
        Toast("正在自检…");
        var (ok, msg) = await InstanceActions.RepairAsync(_current, l => Diag(l));
        Toast((ok ? "✔ " : "✘ ") + msg);
    }

    private void OnUninstallInstance()
    {
        if (_current == null) return;
        var managed = InstanceActions.IsManaged(_current);
        var text = managed
            ? "卸载实例「" + _current.Label + "」？\\n\\n目录：" + _current.Dir
              + "\\n\\n确定会停止服务、删除该目录并移除登记。"
            : "「" + _current.Label + "」是系统安装（" + _current.Source + "），管理器不会删除它。\\n\\n"
              + "需要清理请在文件管理器中操作。现在打开它的目录？";
        var result = MessageBox.Show(this, text, managed ? "卸载实例" : "无法卸载",
            managed ? MessageBoxButton.OKCancel : MessageBoxButton.OK,
            managed ? MessageBoxImage.Warning : MessageBoxImage.Information);
        if (!managed)
        {
            if (result == MessageBoxResult.OK)
                DshHost.OpenFolder(System.IO.Path.GetDirectoryName(_current.Entry) ?? "");
            return;
        }
        if (result != MessageBoxResult.OK) return;
        var (ok, msg) = InstanceActions.Uninstall(_current, deleteDir: true);
        ReloadInstances();
        Toast(msg);
    }
'''

ANCHOR = '    private void OnOpenWindow(object sender, RoutedEventArgs e)'


def main():
    src = io.open(P, encoding='utf-8').read()
    if ANCHOR not in src:
        print('MISS anchor')
        return 1
    src = src.replace(ANCHOR, CODE + '\n' + ANCHOR, 1)
    # More 按钮改成弹菜单
    src = src.replace('    private void OnMore(object sender, RoutedEventArgs e)\n    {\n'
                      '        if (_current == null) return;\n'
                      '        DshHost.OpenFolder(System.IO.Path.GetDirectoryName(_current.Entry) ?? "");\n'
                      '    }',
                      '    private void OnMore(object sender, RoutedEventArgs e) => ShowMoreMenu();')
    # 需要 field + 命名空间
    src = src.replace('    private Popup _themePopup;', '    private Popup _themePopup;\n    private Popup _morePopup;')
    if 'using System.Windows.Shapes;' not in src:
        src = src.replace('using System.Windows.Media.Effects;',
                          'using System.Windows.Media.Effects;\nusing System.Windows.Shapes;')
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('more menu added')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
