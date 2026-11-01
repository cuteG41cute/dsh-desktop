"""设置页的代码：页面切换、信息列表、外观/日志行数、维护动作。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')

CODE = '''
    // ---------------------------------------------------------------- 设置页
    private bool _settingsPage;

    private void OnShowOverview(object sender, RoutedEventArgs e) => ShowPage(false);
    private void OnShowSettings(object sender, RoutedEventArgs e) => ShowPage(true);

    private void ShowPage(bool settings)
    {
        _settingsPage = settings;
        if (ContentScroll != null) ContentScroll.Visibility = settings ? Visibility.Collapsed : Visibility.Visible;
        if (SettingsScroll != null) SettingsScroll.Visibility = settings ? Visibility.Visible : Visibility.Collapsed;
        if (Breadcrumb != null) Breadcrumb.Text = settings ? "管理器设置" : "实例概览";
        if (settings) { FillSettingsInfo(); RefreshSettingsAppearance(); }
    }

    /// <summary>设置页左侧的「管理器信息」列表（键值成对，样式照设计稿的 info-list）。</summary>
    private void FillSettingsInfo()
    {
        if (InfoList == null) return;
        InfoList.Children.Clear();
        var rows = new (string Key, string Value)[]
        {
            ("管理器版本", "v" + typeof(MainWindow).Assembly.GetName().Version),
            ("程序目录", AppContext.BaseDirectory.TrimEnd('\\\\')),
            ("配置目录", System.IO.Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "dsh-manager")),
            ("运行环境", ".NET " + Environment.Version + " · WPF"),
            ("DSH_HOME", DshDiscovery.HomeDir),
            ("实例根目录", _instances.Count > 0
                ? System.IO.Path.GetDirectoryName(System.IO.Path.GetDirectoryName(_instances[0].Entry) ?? "")
                : "—"),
        };
        foreach (var (key, value) in rows)
        {
            var grid = new Grid { MinHeight = 40, Margin = new Thickness(0, 0, 0, 0) };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var k = new TextBlock
            {
                Text = key, FontSize = 10, VerticalAlignment = VerticalAlignment.Center,
                Foreground = (Brush)FindResource("Muted"),
            };
            var v = new TextBlock
            {
                Text = value, FontSize = 9, VerticalAlignment = VerticalAlignment.Center,
                HorizontalAlignment = HorizontalAlignment.Right, TextTrimming = TextTrimming.CharacterEllipsis,
                FontFamily = (FontFamily)FindResource("MonoFont"),
                Foreground = (Brush)FindResource("Text"), MaxWidth = 420,
            };
            var line = new Border
            {
                BorderBrush = (Brush)FindResource("InnerBorder"),
                BorderThickness = new Thickness(0, 0, 0, 1),
                Padding = new Thickness(0, 0, 0, 0),
                Child = grid,
            };
            Grid.SetColumn(k, 0);
            Grid.SetColumn(v, 1);
            grid.Children.Add(k);
            grid.Children.Add(v);
            InfoList.Children.Add(line);
        }
    }

    private void RefreshSettingsAppearance()
    {
        if (SettingsThemeName == null) return;
        SettingsThemeName.Text = ThemeService.Label;
        SettingsModeName.Text = ThemeService.Mode == "night" ? "夜间模式" : "日间模式";
        if (LogLinesBox != null && string.IsNullOrWhiteSpace(LogLinesBox.Text)) LogLinesBox.Text = "800";
    }

    private void OnSettingsChangeTheme(object sender, RoutedEventArgs e)
    {
        ShowPage(false);                 // 主题菜单挂在顶栏的按钮上，先回到仪表盘再弹
        OnThemeTrigger(ThemeTrigger, new RoutedEventArgs());
    }

    private void OnSaveSettings(object sender, RoutedEventArgs e)
    {
        if (int.TryParse(LogLinesBox.Text, out var lines))
        {
            lines = Math.Clamp(lines, 100, 5000);
            LogLinesBox.Text = lines.ToString();
            AppSettings.LogLines = lines;
            AppSettings.Save();
            if (_current != null) RefreshLogs(_current);
            Toast("设置已保存（日志保留 " + lines + " 行）");
        }
        else
        {
            LogLinesBox.Text = AppSettings.LogLines.ToString();
            Toast("日志行数要是数字（100–5000）");
        }
    }

    private void OnOpenManagerLog(object sender, RoutedEventArgs e)
    {
        var dir = System.IO.Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "dsh-manager");
        System.IO.Directory.CreateDirectory(dir);
        DshHost.OpenFolder(dir);
        Toast("已打开管理器数据目录");
    }

    private void OnCopyDiagnostics(object sender, RoutedEventArgs e)
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("=== DSH 管理器诊断 ===");
        sb.AppendLine("版本: " + typeof(MainWindow).Assembly.GetName().Version);
        sb.AppendLine("系统: " + Environment.OSVersion + " / .NET " + Environment.Version);
        sb.AppendLine("DSH_HOME: " + DshDiscovery.HomeDir);
        foreach (var inst in _instances)
            sb.AppendLine($"实例: {inst.Label} | {inst.Source} | dsh {inst.DshVersion} | node {inst.NodeVersion}"
                          + $" | 端口 {inst.Port} | {(inst.Running ? "运行中 PID " + inst.Pid : "已停止")}");
        try
        {
            System.Windows.Clipboard.SetText(sb.ToString());
            Toast("诊断信息已复制到剪贴板");
        }
        catch { Toast("复制失败（剪贴板被占用）"); }
    }

    private void OnCheckUpdate(object sender, RoutedEventArgs e)
    {
        Toast("检查更新：当前是开发版，后续接发布源");
    }
'''

ANCHOR = '    private void OnManagePlugins(object sender, MouseButtonEventArgs e)'


def main():
    src = io.open(P, encoding='utf-8').read()
    if ANCHOR not in src:
        print('MISS anchor')
        return 1
    src = src.replace(ANCHOR, CODE + '\n' + ANCHOR, 1)
    # 刷新日志用设置里的行数
    src = src.replace('var text = DshHost.Tail(inst, 3);', 'var text = DshHost.Tail(inst, AppSettings.LogLines);')
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('settings code added')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
