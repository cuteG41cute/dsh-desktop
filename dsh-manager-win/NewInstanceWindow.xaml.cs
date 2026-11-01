using System;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using DshManager.Services;

namespace DshManager;

public partial class NewInstanceWindow : Window
{
    /// <summary>装完之后发一次（非模态窗口没有 DialogResult，由管理器订阅它刷新列表）。</summary>
    public event Action<string> Created;

    public string CreatedDir { get; private set; } = "";
    private bool _busy;

    public NewInstanceWindow()
    {
        InitializeComponent();
        var def = Path.Combine(InstanceRegistry.DefaultRoot, "dsh-new");
        DirBox.Text = def;
        Loaded += (_, _) =>
        {
            DirBox.Text = def;
            AppendLog("提示：安装会用系统的 npm（PATH 上的 npm.cmd），装到上面的目录里。");
            LoadVersionLists();
            AppendLog("已有的 DSH 安装不需要新建——直接在主界面选它就行。");
        };
    }

    /// <summary>联网取 dsh / Node 的候选版本（拿不到就用内置列表，不阻塞界面）。</summary>
    private async void LoadVersionLists()
    {
        try
        {
            var dsh = await VersionCatalog.DshVersionsAsync(AppendLog);
            DshVersionBox.ItemsSource = dsh;
            if (string.IsNullOrWhiteSpace(DshVersionBox.Text)) DshVersionBox.Text = "latest";
            AppendLog("dsh 版本候选 " + dsh.Count + " 个（" + dsh[0] + " … " + dsh[dsh.Count - 1] + "）");
        }
        catch (Exception ex) { AppendLog("dsh 版本列表失败：" + ex.Message); }
        try
        {
            var node = await VersionCatalog.NodeVersionsAsync(AppendLog);
            NodeVersionBox.ItemsSource = node;
            if (string.IsNullOrWhiteSpace(NodeVersionBox.Text)) NodeVersionBox.Text = VersionCatalog.SystemNode;
            AppendLog("Node 版本候选 " + node.Count + " 个（默认 system = 用系统的 node）");
        }
        catch (Exception ex) { AppendLog("Node 版本列表失败：" + ex.Message); }
    }

    private void AppendLog(string line)
    {
        LogText.Text += line + Environment.NewLine;
        LogScroll.ScrollToEnd();
    }

    private void OnBrowse(object sender, RoutedEventArgs e)
    {
        // WPF 没有文件夹选择器，这里用 WinForms 的（.NET 8 Windows Desktop 自带）
        try
        {
            var dlg = new System.Windows.Forms.FolderBrowserDialog
            {
                Description = "选择实例安装目录",
                UseDescriptionForTitle = true,
            };
            if (Directory.Exists(DirBox.Text)) dlg.SelectedPath = DirBox.Text;
            if (dlg.ShowDialog() == System.Windows.Forms.DialogResult.OK)
            {
                var name = string.IsNullOrWhiteSpace(NameBox.Text) ? "dsh-new" : NameBox.Text.Trim();
                DirBox.Text = Path.Combine(dlg.SelectedPath, name);
            }
        }
        catch (Exception ex) { AppendLog("选择目录失败：" + ex.Message); }
    }

    private async void OnCreate(object sender, RoutedEventArgs e)
    {
        if (_busy) return;
        var name = (NameBox.Text ?? "").Trim();
        var dir = (DirBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(name)) { StatusText.Text = "先填实例名称"; return; }
        if (string.IsNullOrWhiteSpace(dir)) { StatusText.Text = "先选安装目录"; return; }

        var port = 0;
        if (!string.IsNullOrWhiteSpace(PortBox.Text) && !int.TryParse(PortBox.Text, out port))
        {
            StatusText.Text = "端口要是数字"; return;
        }

        _busy = true;
        CreateBtn.IsEnabled = false;
        CancelBtn.IsEnabled = false;
        StatusText.Text = "正在安装…（npm 可能需要几分钟）";
        AppendLog("=== 开始安装 ===");

        var nodeVer = (NodeVersionBox.Text ?? "").Trim();
        var (ok, msg) = await InstanceInstaller.InstallAsync(
            dir, DshVersionBox.Text ?? "latest", AppendLog, port,
            string.IsNullOrWhiteSpace(nodeVer) ? VersionCatalog.SystemNode : nodeVer);
        _busy = false;
        CreateBtn.IsEnabled = true;
        CancelBtn.IsEnabled = true;
        StatusText.Text = msg;
        AppendLog((ok ? "✔ " : "✘ ") + msg);
        if (ok)
        {
            CreatedDir = dir;
            Created?.Invoke(dir);
            Close();
        }
    }

    private void OnClose(object sender, RoutedEventArgs e)
    {
        if (_busy) return;
        Close();
    }

    private void OnDrag(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Left) return;
        for (var d = e.OriginalSource as DependencyObject; d != null; d = VisualTreeHelper.GetParent(d))
            if (d is Button || d is TextBox) return;
        try { DragMove(); } catch { }
    }
}
