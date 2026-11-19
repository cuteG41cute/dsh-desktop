using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using DshManager.Services;
using DshManager.ViewModels;

namespace DshManager;

/// <summary>「从备份新建」五步向导。</summary>
public partial class RestoreWizardWindow : Window
{
    private readonly RegistryEntry _instance;
    private readonly string _home;
    private int _step = 1;
    private ProjectMigration.ProjectInfo? _pending;
    private string _bundle = "";
    private string _newName = "";

    public RestoreWizardWindow(RegistryEntry instance)
    {
        InitializeComponent();
        _instance = instance;
        _home = ProjectCatalog.HomeFor(instance);
        TargetLabel.Text = instance.Label;
        TargetMeta.Text = $"DSH {instance.DshVersion} · 端口 {instance.Port}";
        TargetHome.Text = _home;
        Step2Dir.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "dsh-backup");
        Step3Dir.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "Projects");
        SetStep(1);
    }

    private void SetStep(int step)
    {
        _step = Math.Clamp(step, 1, 5);
        foreach (var panel in new[] { Step1Panel, Step2Panel, Step3Panel, Step4Panel, Step5Panel })
            panel.Visibility = Visibility.Collapsed;
        switch (_step)
        {
            case 1: Step1Panel.Visibility = Visibility.Visible; break;
            case 2: Step2Panel.Visibility = Visibility.Visible; LoadBundles(); break;
            case 3: Step3Panel.Visibility = Visibility.Visible; ShowPreview(); break;
            case 4: Step4Panel.Visibility = Visibility.Visible; break;
            case 5: Step5Panel.Visibility = Visibility.Visible; break;
        }
        var dots = new[] { Dot1, Dot2, Dot3, Dot4, Dot5 };
        var labels = new[] { Label1, Label2, Label3, Label4, Label5 };
        for (var i = 0; i < dots.Length; i++)
        {
            var index = i + 1;
            var done = index < _step;
            var active = index == _step;
            labels[i].Text = done ? "✓" : index.ToString();
            dots[i].Background = (Brush)FindResource(done || active ? "Accent" : "InnerBorder");
            labels[i].Foreground = (Brush)FindResource(done || active ? "OnAccent" : "Muted");
        }
        var captions = new[] { "选择来源", "选择备份", "预览与目录", "导入", "完成" };
        _ = captions;
        BackBtn.Visibility = _step > 1 && _step < 4 ? Visibility.Visible : Visibility.Collapsed;
        NextBtn.Visibility = _step < 4 ? Visibility.Visible : Visibility.Collapsed;
        if (_step == 4) NextBtn.Visibility = Visibility.Collapsed;
        if (_step == 3) NextBtn.Content = "开始导入";
        if (_step == 2) NextBtn.Content = "下一步";
    }

    private void OnBack(object sender, RoutedEventArgs e) => SetStep(_step - 1);

    private void OnNext(object sender, RoutedEventArgs e)
    {
        if (_step == 1) { SetStep(2); return; }
        if (_step == 2)
        {
            if (string.IsNullOrEmpty(_bundle)) { Toast("先选择一个备份包"); return; }
            SetStep(3);
            return;
        }
        if (_step == 3) { StartImport(); }
    }

    private void LoadBundles()
    {
        BundleList.Children.Clear();
        var dir = Step2Dir.Text?.Trim() ?? "";
        BundleEmpty.Visibility = Visibility.Visible;
        if (!Directory.Exists(dir)) return;
        foreach (var file in Directory.GetFiles(dir, "*.dshproj").OrderByDescending(f => File.GetLastWriteTime(f)))
        {
            var m = ProjectMigration.ReadManifest(file);
            var title = m?.Title ?? Path.GetFileNameWithoutExtension(file);
            var size = new FileInfo(file).Length / 1024.0 / 1024.0;
            var row = new Button
            {
                Margin = new Thickness(0, 0, 0, 6),
                Padding = new Thickness(10, 8, 10, 8),
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Background = (Brush)FindResource("CardSolid"),
                BorderBrush = (Brush)FindResource("InnerBorder"),
                BorderThickness = new Thickness(1),
                Tag = file,
                Content = new StackPanel
                {
                    Children =
                    {
                        new TextBlock { Text = title, FontSize = 10, FontWeight = FontWeights.SemiBold,
                            Foreground = (Brush)FindResource("Text") },
                        new TextBlock { Text = $"{m?.CreatedAt} · {size:F1} MB · {Path.GetFileName(file)}",
                            FontSize = 8, Margin = new Thickness(0, 3, 0, 0),
                            Foreground = (Brush)FindResource("Muted") },
                    },
                },
            };
            row.Click += (_, _) =>
            {
                _bundle = file;
                Step2Sel.Text = title + " · " + Path.GetFileName(file);
                BundleEmpty.Visibility = Visibility.Collapsed;
            };
            BundleList.Children.Add(row);
        }
        if (BundleList.Children.Count == 0) BundleEmpty.Visibility = Visibility.Visible;
    }

    private void ShowPreview()
    {
        var m = ProjectMigration.ReadManifest(_bundle);
        _newName = (m?.Title ?? "项目") + "-恢复";
        Step3Name.Text = _newName;
        PrevDir.Text = Step3Dir.Text;
        PrevInfo.Text = $"来源设备 {m?.DeviceShort} · 备份时间 {m?.CreatedAt} · 包体 {new FileInfo(_bundle).Length / 1024.0 / 1024.0:F1} MB";
        Step3Target.Text = _instance.Label;
    }

    private void StartImport()
    {
        var dir = Step3Dir.Text?.Trim() ?? "";
        if (dir.Length == 0) { Toast("先选择目标目录"); return; }
        var name = Step3Name.Text?.Trim() ?? "";
        if (name.Length == 0) { Toast("填写新项目名称"); return; }
        SetStep(4);
        ImportProgress.Value = 5;
        ImportStage.Text = "正在解包备份";
        System.Threading.Tasks.Task.Run(() =>
        {
            var (ok, msg) = ProjectMigration.Import(_bundle, dir,
                s => Dispatcher.BeginInvoke(new Action(() =>
                {
                    ImportStage.Text = s;
                    ImportProgress.Value = Math.Min(92, ImportProgress.Value + 16);
                })), _home);
            Dispatcher.BeginInvoke(new Action(() =>
            {
                ImportProgress.Value = 100;
                SetStep(5);
                DoneText.Text = msg;
            }));
        });
    }

    private void OnBrowseSource(object sender, RoutedEventArgs e)
    {
        var pick = new System.Windows.Forms.FolderBrowserDialog { Description = "选择备份所在目录" };
        if (pick.ShowDialog() == System.Windows.Forms.DialogResult.OK)
        {
            Step2Dir.Text = pick.SelectedPath;
            LoadBundles();
        }
    }

    private void OnBrowseTarget(object sender, RoutedEventArgs e)
    {
        var pick = new System.Windows.Forms.FolderBrowserDialog { Description = "选择项目要放到哪个目录" };
        if (pick.ShowDialog() == System.Windows.Forms.DialogResult.OK)
        {
            Step3Dir.Text = pick.SelectedPath;
            PrevDir.Text = pick.SelectedPath;
        }
    }

    private void OnRestart(object sender, RoutedEventArgs e)
    {
        Toast("实例正在重启，项目随后可见");
        Close();
    }

    private void OnCloseWizard(object sender, RoutedEventArgs e) => Close();

    private void Toast(string msg)
    {
        ToastText.Text = msg;
        ToastBox.Visibility = Visibility.Visible;
        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2.4) };
        timer.Tick += (_, _) => { timer.Stop(); ToastBox.Visibility = Visibility.Collapsed; };
        timer.Start();
    }
}
