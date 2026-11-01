using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using DshManager.Services;

namespace DshManager;

public partial class PluginWindow : Window
{
    private readonly DshInstance _inst;
    private List<PluginInfo> _items = new();
    private PluginInfo _selected;
    private bool _busy;

    public PluginWindow(DshInstance inst)
    {
        InitializeComponent();
        _inst = inst;
        Loaded += OnLoaded;
        ThemeService.ThemeChanged += Render;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        var cached = PluginCatalog.LoadCached(out var fetched);
        if (cached.Count > 0)
        {
            PluginCatalog.MarkInstalled(_inst, cached);
            _items = cached;
            SourceLine.Text = "来自 GitHub · topic: dsh-plugin · 缓存于 " + fetched;
            Render();
            SetStatus("使用缓存，" + _items.Count + " 个插件；正在后台刷新…");
        }
        else SetStatus("正在从 GitHub 拉取插件列表…");

        // 后台刷新（失败也保留缓存）
        try
        {
            var fresh = await PluginCatalog.RefreshAsync();
            PluginCatalog.MarkInstalled(_inst, fresh);
            _items = fresh;
            SourceLine.Text = "来自 GitHub · topic: dsh-plugin · 抓取于 " + DateTime.Now.ToString("HH:mm:ss");
            Render();
            SetStatus("共 " + _items.Count + " 个插件");
        }
        catch (Exception ex)
        {
            if (_items.Count == 0) SetStatus("拉取失败：" + ex.Message + "（可先点「刷新 GitHub 列表」重试）");
            else SetStatus("后台刷新失败：" + ex.Message);
        }
    }

    // ---------------------------------------------------------------- 渲染
    /// <summary>安全取主题资源：缺键时给兜底色，避免一行渲染失败带崩整个列表。</summary>
    private Brush Res(string key, Brush fallback = null)
    {
        try { return TryFindResource(key) as Brush ?? fallback ?? Brushes.Black; }
        catch { return fallback ?? Brushes.Black; }
    }

    private void Render()
    {
        if (Rows == null) return;
        Rows.Children.Clear();
        if (_items.Count == 0)
        {
            Rows.Children.Add(new TextBlock
            {
                Text = "还没有拉取到插件列表", Margin = new Thickness(6, 18, 6, 0),
                FontSize = 10, Foreground = Res("Muted"),
            });
            return;
        }

        foreach (var p in _items)
        {
            var row = new Grid { Height = 46, Margin = new Thickness(0, 2, 0, 2) };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(190) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(110) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(90) });

            var name = new TextBlock
            {
                Text = p.Id, FontSize = 11, FontWeight = FontWeights.SemiBold,
                VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis,
                Foreground = Res("Text"),
            };
            var repo = new TextBlock
            {
                Text = (string.IsNullOrEmpty(p.Repo) ? p.Desc : p.Repo + " — " + p.Desc),
                FontSize = 9.5, VerticalAlignment = VerticalAlignment.Center,
                TextTrimming = TextTrimming.CharacterEllipsis,
                Foreground = Res("Muted"),
            };
            var status = new TextBlock
            {
                Text = p.Status, FontSize = 9.5, VerticalAlignment = VerticalAlignment.Center,
                Foreground = Res(p.InPatch ? "Success" : (p.Installed ? "Muted" : "Subtle")),
            };
            var ver = new TextBlock
            {
                Text = string.IsNullOrEmpty(p.InstalledVersion) ? "—" : p.InstalledVersion,
                FontSize = 9.5, VerticalAlignment = VerticalAlignment.Center,
                FontFamily = (FontFamily)FindResource("MonoFont"),
                Foreground = Res("Muted"),
            };

            Grid.SetColumn(name, 0);
            Grid.SetColumn(repo, 1);
            Grid.SetColumn(status, 2);
            Grid.SetColumn(ver, 3);
            row.Children.Add(name);
            row.Children.Add(repo);
            row.Children.Add(status);
            row.Children.Add(ver);

            var bg = p == _selected ? "AccentSoft" : "Card";
            var border = new Border
            {
                Padding = new Thickness(12, 0, 12, 0),
                CornerRadius = new CornerRadius(9),
                Background = Res(bg),
                BorderBrush = Res(p == _selected ? "InnerBorder" : "Card"),
                BorderThickness = new Thickness(1),
                Child = row,
                Cursor = Cursors.Hand,
                ToolTip = p.Repo,
            };
            border.MouseLeftButtonDown += (_, _) =>
            {
                if (_busy) return;
                _selected = p;
                Render();
                UpdateButtons();
            };
            Rows.Children.Add(border);
        }
        UpdateButtons();
    }

    private void UpdateButtons()
    {
        var has = _selected != null;
        InstallBtn.IsEnabled = has && !_busy;
        UninstallBtn.IsEnabled = has && _selected.Installed && !_busy;
        RepoBtn.IsEnabled = has && !string.IsNullOrEmpty(_selected.Repo) && !_busy;
        RefreshStateBtn.IsEnabled = !_busy;
        RefreshGhBtn.IsEnabled = !_busy;
        InstallBtn.Content = _selected == null ? "安装 / 更新"
            : (_selected.Installed ? "更新到最新" : "安装");
    }

    private void SetStatus(string text) { if (StatusLine != null) StatusLine.Text = text; }

    // ---------------------------------------------------------------- 动作
    private void OnRefreshState(object sender, RoutedEventArgs e)
    {
        PluginCatalog.MarkInstalled(_inst, _items);
        Render();
        SetStatus("已刷新安装状态");
    }

    private async void OnInstall(object sender, RoutedEventArgs e)
    {
        if (_selected == null || _busy) return;
        _busy = true;
        UpdateButtons();
        SetStatus("正在安装 " + _selected.Id + "…");
        var (ok, msg) = await PluginCatalog.InstallAsync(_inst, _selected, m => SetStatus(m));
        _busy = false;
        PluginCatalog.MarkInstalled(_inst, _items);
        Render();
        SetStatus(msg + (ok ? "（重启实例的服务后生效）" : ""));
    }

    private void OnUninstall(object sender, RoutedEventArgs e)
    {
        if (_selected == null || _busy) return;
        if (MessageBox.Show(this, "卸载 " + _selected.Id + "？\n目录与 patch 行都会被移除，插件数据不受影响。",
                "卸载插件", MessageBoxButton.OKCancel, MessageBoxImage.Warning) != MessageBoxResult.OK) return;
        var (ok, msg) = PluginCatalog.Uninstall(_inst, _selected);
        PluginCatalog.MarkInstalled(_inst, _items);
        Render();
        SetStatus(msg);
    }

    private void OnOpenRepo(object sender, RoutedEventArgs e)
    {
        if (_selected == null || string.IsNullOrEmpty(_selected.Repo)) return;
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(
                "https://github.com/" + _selected.Repo) { UseShellExecute = true });
        }
        catch { }
    }

    private async void OnRefreshGithub(object sender, RoutedEventArgs e)
    {
        if (_busy) return;
        _busy = true;
        UpdateButtons();
        SetStatus("正在从 GitHub 拉取列表…");
        try
        {
            var fresh = await PluginCatalog.RefreshAsync();
            PluginCatalog.MarkInstalled(_inst, fresh);
            _items = fresh;
            _selected = null;
            SourceLine.Text = "来自 GitHub · topic: dsh-plugin · 抓取于 " + DateTime.Now.ToString("HH:mm:ss");
            Render();
            SetStatus("共 " + _items.Count + " 个插件");
        }
        catch (Exception ex)
        {
            SetStatus("刷新失败：" + ex.Message);
        }
        finally
        {
            _busy = false;
            UpdateButtons();
        }
    }

    private void OnClose(object sender, RoutedEventArgs e) => Close();

    private void OnDrag(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Left) return;
        for (var d = e.OriginalSource as DependencyObject; d != null; d = VisualTreeHelper.GetParent(d))
            if (d is Button) return;
        try { DragMove(); } catch { }
    }
}
