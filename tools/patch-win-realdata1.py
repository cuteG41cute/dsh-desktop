"""把 MainWindow 从「示例数据」接到真实 DSH 安装（发现/启停/打开/日志）。"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')

OLD_DATA = '''    /// <summary>界面上要显示的实例（第一阶段先用示例数据，接后端后换成真实实例）。</summary>
    private sealed class InstanceVm
    {
        public string Id { get; init; }
        public string Initials { get; init; }
        public string Version { get; init; }
        public bool Running { get; init; }
        public string Path { get; init; }
        public int Port { get; init; }
        public int Pid { get; init; }
        public string DshVersion { get; init; }
        public string NodeVersion { get; init; }
    }

    private readonly List<InstanceVm> _instances = new()
    {
        new InstanceVm
        {
            Id = "deepseek-harness-1", Initials = "D1", Version = "v0.2.1-rc.5", Running = true,
            Path = @"C:\\Users\\twinblade\\Programs\\deepseek-harness-1", Port = 3080, Pid = 0,
            DshVersion = "0.2.1-rc.5", NodeVersion = "26.13.0"
        },
    };

    private InstanceVm _current;'''

NEW_DATA = '''    /// <summary>发现的 DSH 安装（npx 缓存 / 全局 npm / profile / PATH）。</summary>
    private List<DshInstance> _instances = new();
    private DshInstance _current;
    private DispatcherTimer _poll;'''

REPLACEMENTS = [
    (OLD_DATA, NEW_DATA),
]

# OnLoaded：接真实数据
OLD_LOADED = '''    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        ApplyRoundedCorners();
        BuildInstanceList();
        ShowInstance(_current);
        BuildSampleLogs();'''
NEW_LOADED = '''    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        ApplyRoundedCorners();
        ReloadInstances();
        _poll = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2.5) };
        _poll.Tick += (_, _) => PollCurrent();
        _poll.Start();'''

# BuildInstanceList / ShowInstance / BuildSampleLogs 整体替换
OLD_BUILD = '''    private void BuildInstanceList()
    {'''
NEW_BUILD = '''    /// <summary>重新扫描本机 DSH 安装。</summary>
    private void ReloadInstances()
    {
        _instances = DshDiscovery.Scan().ToList();
        _current = _instances.FirstOrDefault();
        BuildInstanceList();
        if (_current != null) ShowInstance(_current);
        else ShowEmptyState();
    }

    private void ShowEmptyState()
    {
        InstanceTitle.Text = "未发现 DSH 安装";
        AvatarText.Text = "?";
        InstallPath.Text = "扫描位置：npx 缓存 / %APPDATA%\\\\npm / %DSH_HOME%\\\\profiles / PATH";
        DshVersion.Text = "—";
        NodeVersion.Text = "—";
        PortValue.Text = "—";
        PidValue.Text = "—";
        RunState.Text = "未安装";
        RunState.Foreground = (Brush)FindResource("Muted");
        StatusBadgeText.Text = "未安装";
        StatusBadge.Background = (Brush)FindResource("AccentSoft");
        StatusBadgeText.Foreground = (Brush)FindResource("Muted");
        LogBody.Children.Clear();
        LogCount.Text = "0";
    }

    private static string InitialsFor(DshInstance inst)
    {
        var name = inst.Source switch
        {
            "npx 缓存" => "NPX",
            "全局安装" => "GLB",
            "profile" => "PRF",
            "PATH" => "PTH",
            _ => "DSH",
        };
        return name;
    }

    private void PollCurrent()
    {
        if (_current == null) return;
        DshDiscovery.Probe(_current);
        ShowInstance(_current);
        RefreshLogs(_current);
        BuildInstanceList();
    }

    private void RefreshLogs(DshInstance inst)
    {
        var text = DshHost.Tail(inst, 3);
        LogBody.Children.Clear();
        if (string.IsNullOrWhiteSpace(text))
        {
            LogCount.Text = "0";
            LogBody.Children.Add(new TextBlock
            {
                Text = "（还没有日志：服务由管理器启动后这里会实时显示）",
                FontSize = 8.5, Margin = new Thickness(0, 6, 0, 6),
                Foreground = (Brush)FindResource("Muted"),
            });
            return;
        }
        var lines = text.Split('\\n');
        foreach (var raw in lines)
        {
            var line = raw.TrimEnd();
            if (line.Length == 0) continue;
            AddLogLine(DateTime.Now.ToString("HH:mm:ss"), "信息", line);
        }
        LogCount.Text = lines.Length.ToString();
    }

    private void AddLogLine(string time, string level, string text)
    {
        var grid = new Grid { Height = 27, Margin = new Thickness(0, 1, 0, 0) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(70) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

        var t = new TextBlock
        {
            Text = time, FontSize = 8.5, FontFamily = (FontFamily)FindResource("MonoFont"),
            Foreground = (Brush)FindResource("Subtle"), VerticalAlignment = VerticalAlignment.Center,
        };
        var levelText = new TextBlock
        {
            Text = level, FontSize = 7.5, FontWeight = FontWeights.SemiBold,
            HorizontalAlignment = HorizontalAlignment.Center,
            Foreground = (Brush)FindResource("Accent"),
        };
        var levelBorder = new Border
        {
            CornerRadius = new CornerRadius(4), Padding = new Thickness(4, 2, 4, 2),
            VerticalAlignment = VerticalAlignment.Center, Child = levelText,
            MinWidth = 29, Margin = new Thickness(0, 0, 11, 0),
            Background = (Brush)FindResource("AccentSoft"),
        };
        var msg = new TextBlock
        {
            Text = text, FontSize = 8.5, VerticalAlignment = VerticalAlignment.Center,
            Foreground = (Brush)FindResource("Text"), TextTrimming = TextTrimming.CharacterEllipsis,
        };
        Grid.SetColumn(t, 0);
        Grid.SetColumn(levelBorder, 1);
        Grid.SetColumn(msg, 2);
        grid.Children.Add(t);
        grid.Children.Add(levelBorder);
        grid.Children.Add(msg);
        LogBody.Children.Add(grid);
    }

    private void BuildInstanceList()
    {'''


def main():
    src = io.open(P, encoding='utf-8').read()
    for old, new in REPLACEMENTS:
        if old not in src:
            print('MISS data block')
            return 1
        src = src.replace(old, new, 1)
    if OLD_LOADED not in src:
        print('MISS loaded')
        return 1
    src = src.replace(OLD_LOADED, NEW_LOADED, 1)
    if OLD_BUILD not in src:
        print('MISS build')
        return 1
    src = src.replace(OLD_BUILD, NEW_BUILD, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('wired real data (part 1)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
