"""接真实数据的第 2 步：实例列表/详情用 DshInstance，动作按钮接 DshHost。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml.cs')

PAIRS = [
    # using
    ('using System.Runtime.InteropServices;',
     'using System.Linq;\nusing System.Runtime.InteropServices;'),
    ('using System.Windows.Media.Effects;',
     'using System.Windows.Media.Effects;\nusing System.Windows.Threading;'),

    # 列表项字段
    ('                Text = inst.Initials, FontSize = 10, FontWeight = FontWeights.Bold,',
     '                Text = InitialsFor(inst), FontSize = 10, FontWeight = FontWeights.Bold,'),
    ('                Text = inst.Id, FontSize = 11.5, FontWeight = FontWeights.SemiBold,',
     '                Text = inst.Label, FontSize = 11.5, FontWeight = FontWeights.SemiBold,'),
    ('                Text = inst.Version, FontSize = 10, Margin = new Thickness(0, 4, 0, 0),',
     '                Text = "dsh " + (string.IsNullOrEmpty(inst.DshVersion) ? "?" : inst.DshVersion)\n'
     '                       + " · " + inst.Source, FontSize = 10, Margin = new Thickness(0, 4, 0, 0),'),

    # ShowInstance
    ('''    private void ShowInstance(InstanceVm inst)
    {
        InstanceTitle.Text = inst.Id;
        AvatarText.Text = inst.Initials;
        InstallPath.Text = inst.Path;
        DshVersion.Text = inst.DshVersion;
        NodeVersion.Text = inst.NodeVersion;
        PortValue.Text = inst.Port.ToString();
        PidValue.Text = inst.Pid > 0 ? inst.Pid.ToString() : "—";''',
     '''    private void ShowInstance(DshInstance inst)
    {
        InstanceTitle.Text = inst.Label;
        AvatarText.Text = InitialsFor(inst);
        InstallPath.Text = inst.Entry;
        DshVersion.Text = string.IsNullOrEmpty(inst.DshVersion) ? "?" : inst.DshVersion;
        NodeVersion.Text = string.IsNullOrEmpty(inst.NodeVersion) ? "?" : inst.NodeVersion;
        PortValue.Text = inst.Port.ToString();
        PidValue.Text = inst.Pid > 0 ? inst.Pid.ToString() : "—";'''),

    # 动作按钮
    ('''    private void OnOpenWindow(object sender, RoutedEventArgs e) { }
    private void OnMore(object sender, RoutedEventArgs e) { }
    private void OnRestartService(object sender, RoutedEventArgs e) { }
    private void OnStopService(object sender, RoutedEventArgs e) { }''',
     '''    private void OnOpenWindow(object sender, RoutedEventArgs e)
    {
        if (_current == null) return;
        DshHost.OpenWindow(_current, out var msg);
        RefreshLogs(_current);
        Toast(msg);
    }

    private void OnMore(object sender, RoutedEventArgs e)
    {
        if (_current == null) return;
        DshHost.OpenFolder(System.IO.Path.GetDirectoryName(_current.Entry) ?? "");
    }

    private void OnRestartService(object sender, RoutedEventArgs e)
    {
        if (_current == null) return;
        DshHost.Stop(_current, out _);
        DshHost.Start(_current, out var msg);
        PollCurrent();
        Toast(msg);
    }

    private void OnStopService(object sender, RoutedEventArgs e)
    {
        if (_current == null) return;
        DshHost.Stop(_current, out var msg);
        PollCurrent();
        Toast(msg);
    }

    /// <summary>启动/停止服务（左侧快捷控制里的「重启/停止」之外，列表双击也能起停）。</summary>
    private void StartCurrent()
    {
        if (_current == null) return;
        DshHost.Start(_current, out var msg);
        PollCurrent();
        Toast(msg);
    }

    private void Toast(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        RuntimeLine.Text = text.Length > 46 ? text.Substring(0, 46) + "…" : text;
    }'''),
]


def main():
    src = io.open(P, encoding='utf-8').read()
    misses = []
    for old, new in PAIRS:
        if old not in src:
            misses.append(old.splitlines()[0][:60])
            continue
        src = src.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('misses:', misses if misses else 'none')


if __name__ == '__main__':
    main()
