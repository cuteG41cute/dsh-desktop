using System;
using System.Linq;
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
    private bool _dirEdited;
    private bool _suppressDir;

    public NewInstanceWindow()
    {
        InitializeComponent();
        var def = UniqueDir("dsh-new");
        SetDirSilently(def);
        Loaded += (_, _) =>
        {
            SetDirSilently(UniqueDir(FileNameOf(DirBox.Text) is { Length: > 0 } n ? n : "dsh-new"));
            _ = LoadVersionLists();
        };
    }

    /// <summary>程序自己改目录时不要把「用户手动改过」标记点亮。</summary>
    private void SetDirSilently(string value)
    {
        _suppressDir = true;
        try { DirBox.Text = value; } finally { _suppressDir = false; }
    }

    /// <summary>目录名（不带末尾分隔符）。</summary>
    private static string FileNameOf(string dir)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(dir)) return "";
            return Path.GetFileName(Path.TrimEndingDirectorySeparator(dir.Trim()));
        }
        catch { return ""; }
    }

    /// <summary>
    /// 生成一个**没有被占用**的实例目录：
    /// 目录已存在（非空）、或已被登记成实例 → 依次试 name-2、name-3…
    /// </summary>
    private static string UniqueDir(string baseName)
    {
        var root = InstanceRegistry.DefaultRoot;
        var name = string.IsNullOrWhiteSpace(baseName) ? "dsh-new" : baseName.Trim();
        var regs = InstanceRegistry.Load();
        bool Taken(string path)
        {
            try
            {
                if (Directory.Exists(path) && Directory.GetFileSystemEntries(path).Length > 0) return true;
                if (regs.Any(r => string.Equals(
                        Path.GetFullPath(r.Dir ?? ""), Path.GetFullPath(path),
                        StringComparison.OrdinalIgnoreCase))) return true;
            }
            catch { }
            return false;
        }
        var candidate = Path.Combine(root, name);
        if (!Taken(candidate)) return candidate;
        for (var i = 2; i < 100; i++)
        {
            candidate = Path.Combine(root, name + "-" + i);
            if (!Taken(candidate)) return candidate;
        }
        return candidate;
    }

    /// <summary>联网取 dsh / Node 的候选版本（拿不到就用内置列表，不阻塞界面）。</summary>
    private async System.Threading.Tasks.Task LoadVersionLists()
    {
        try
        {
            var refs = await VersionCatalog.GitRefsAsync(AppendLog);
            DshVersionBox.ItemsSource = refs;
            DshVersionBox.Text = "master";
            AppendLog("仓库版本候选 " + refs.Count + " 个（默认 master）");
        }
        catch (Exception ex) { AppendLog("dsh 版本列表失败：" + ex.Message); }
        try
        {
            var node = await VersionCatalog.NodeVersionsAsync(AppendLog);
            NodeVersionBox.ItemsSource = node;
            if (string.IsNullOrWhiteSpace(NodeVersionBox.Text)) NodeVersionBox.Text = "latest";
            AppendLog("Node 版本候选 " + node.Count + " 个（默认 system = 用系统的 node）");
        }
        catch (Exception ex) { AppendLog("Node 版本列表失败：" + ex.Message); }
    }

    /// <summary>底部「更新 dsh / Node 版本」：重新拉一次候选列表。</summary>
    private async void OnRefreshVersions(object sender, RoutedEventArgs e)
    {
        try
        {
            RefreshVersionsBtn.IsEnabled = false;
            StatusText.Text = "正在重新获取版本列表…";
            AppendLog("=== 重新获取 dsh / Node 版本列表 ===");
            await LoadVersionLists();
            StatusText.Text = "版本列表已更新";
        }
        catch (Exception ex)
        {
            StatusText.Text = "更新版本列表失败：" + ex.Message;
        }
        finally
        {
            RefreshVersionsBtn.IsEnabled = true;
        }
    }

    private void AppendLog(string line)
    {
        // npm 的输出是在**后台线程**（DataReceived）里回调进来的，直接摸 WPF 控件会抛
        // "The calling thread cannot access this object" —— 之前就是这么崩的。
        if (!Dispatcher.CheckAccess())
        {
            try { Dispatcher.BeginInvoke(new Action(() => AppendLog(line))); } catch { }
            return;
        }
        try
        {
            // 只有在“真正开始干活”（安装/更新版本）时才把日志卡片露出来；
            // 启动提示、版本列表加载这些背景日志不显示，避免出现一块看着像空框的区域。
            if (_busy && LogCard != null && LogCard.Visibility != Visibility.Visible) LogCard.Visibility = Visibility.Visible;
            LogText.Text += (line ?? "") + Environment.NewLine;
            LogScroll.ScrollToEnd();
        }
        catch { }
    }

    private void OnNameChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        try
        {
            var name = (NameBox.Text ?? "").Trim();
            if (string.IsNullOrWhiteSpace(name)) return;
            if (!_dirEdited) DirBox.Text = UniqueDir(name);
        }
        catch { }
    }

    private void OnDirChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        if (_suppressDir) return;                 // 程序设置，不算用户编辑
        // 用户自己动过目录就不再自动覆盖
        if (!string.IsNullOrWhiteSpace(DirBox.Text)) _dirEdited = true;
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
                SetDirSilently(Path.Combine(dlg.SelectedPath, name));
        _dirEdited = true;
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

        // 源码安装依赖 git；干净系统上常常没有，提前检查，别让用户看 .NET 的原始异常
        try
        {
            var gitCheck = new System.Diagnostics.ProcessStartInfo("git", "--version")
            {
                RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false, CreateNoWindow = true,
            };
            using var gp = System.Diagnostics.Process.Start(gitCheck);
            gp.WaitForExit(8000);
            if (gp.ExitCode != 0)
            {
                StatusText.Text = "没有可用的 Git，请先安装 Git for Windows";
                AppendLog("✘ git --version 返回 " + gp.ExitCode);
                return;
            }
        }
        catch
        {
            StatusText.Text = "没找到 Git，请先安装 Git for Windows（https://git-scm.com/download/win）";
            AppendLog("✘ 系统里没有 git 命令，源码安装无法继续");
            return;
        }

        // 安装目录必须是「干净的新目录」：已存在非空、或有 dsh 安装、或已登记为实例，一律拒绝。
        try
        {
            dir = Path.GetFullPath(dir.Trim());
            SetDirSilently(dir);
            var looksLikeInstance =
                File.Exists(Path.Combine(dir, "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js"))
                || File.Exists(Path.Combine(dir, "app", "apps", "cli", "src", "bin.ts"))
                || Directory.Exists(Path.Combine(dir, "dsh-home"));
            var registered = InstanceRegistry.Load().Any(r => string.Equals(
                Path.GetFullPath(r.Dir ?? ""), dir, StringComparison.OrdinalIgnoreCase));
            if (registered || looksLikeInstance)
            {
                StatusText.Text = "这个目录里已经有一个 dsh 实例了，请换一个目录";
                AppendLog("✘ " + dir + " 已经是实例目录（登记=" + registered + "，检出=" + looksLikeInstance + "）");
                return;
            }
            if (Directory.Exists(dir) && Directory.GetFileSystemEntries(dir).Length > 0)
            {
                StatusText.Text = "目录已存在且不为空，请换一个目录（例如 " + UniqueDir(name) + "）";
                AppendLog("✘ " + dir + " 非空，拒绝安装");
                return;
            }
        }
        catch (Exception ex)
        {
            StatusText.Text = "安装目录不合法：" + ex.Message;
            return;
        }

        var port = 0;
        if (!string.IsNullOrWhiteSpace(PortBox.Text) && !int.TryParse(PortBox.Text, out port))
        {
            StatusText.Text = "端口要是数字"; return;
        }
        if (port > 0)
        {
            // 端口不能被别的实例占着，也不能已被系统监听
            var busy = DshDiscovery.Scan().FirstOrDefault(i => i.Port == port);
            if (busy != null)
            {
                StatusText.Text = "端口 " + port + " 已被实例「" + busy.Label + "」使用，请换一个";
                AppendLog("✘ 端口 " + port + " 已被「" + busy.Label + "」占用");
                return;
            }
            try
            {
                var l = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, port);
                l.Start(); l.Stop();
            }
            catch
            {
                StatusText.Text = "端口 " + port + " 已被占用（系统里别的程序在监听）";
                AppendLog("✘ 端口 " + port + " 已被别的程序监听");
                return;
            }
        }

        _busy = true;
        CreateBtn.IsEnabled = false;
        CancelBtn.IsEnabled = false;
        StatusText.Text = "正在安装…（npm 可能需要几分钟）";
        AppendLog("=== 开始安装 ===");

        var nodeVer = (NodeVersionBox.Text ?? "").Trim();
        // 只保留「官方仓库源码」这一条路：实例必须自带 portable Node。
        if (string.IsNullOrWhiteSpace(nodeVer) || nodeVer == VersionCatalog.SystemNode)
        {
            nodeVer = "latest";
            AppendLog("Node 版本留空/选了 system → 自动使用 latest（源码实例必须自带 Node）");
        }
        StatusText.Text = "正在克隆官方仓库并构建…（pnpm install + build，通常十几分钟）";
        var gitRef = (DshVersionBox.Text ?? "").Trim();
        if (string.IsNullOrWhiteSpace(gitRef)) gitRef = "master";
        var existedBefore = Directory.Exists(dir);
        var (ok, msg) = await InstanceInstaller.InstallSourceAsync(dir, nodeVer, AppendLog, port, gitRef);
        if (!ok && !existedBefore)
        {
            // 半成品目录留着会挡住下一次创建（我们的「目录必须为空」校验）
            try
            {
                if (Directory.Exists(dir) && Directory.GetFileSystemEntries(dir).Length > 0)
                {
                    Directory.Delete(dir, true);
                    AppendLog("已清理未完成的目录：" + dir);
                }
            }
            catch { }
        }
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
