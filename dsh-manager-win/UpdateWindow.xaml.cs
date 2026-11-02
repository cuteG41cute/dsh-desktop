using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;

namespace DshManager
{
    /// <summary>
    /// 更新 dsh：列出版本让用户自己选（可升可降），风格跟随主窗口主题。
    /// </summary>
    public partial class UpdateWindow : Window
    {
        private readonly Services.DshInstance _inst;
        private readonly List<string> _versions;

        public string SelectedVersion { get; private set; }

        public UpdateWindow(Services.DshInstance inst, IEnumerable<string> versions)
        {
            InitializeComponent();
            _inst = inst;
            var cur = inst.DshVersion ?? "";
            _versions = versions?
                .Where(v => !string.IsNullOrWhiteSpace(v))
                .Distinct()
                .ToList() ?? new List<string>();

            SubtitleText.Text = "实例 " + inst.Label + " · 当前版本 " + (string.IsNullOrWhiteSpace(cur) ? "未知" : cur)
                                + " · 来源 " + inst.Source;
            VersionList.ItemsSource = _versions.Select(v => new VersionRow
            {
                Text = v,
                IsCurrent = string.Equals(v, cur, StringComparison.OrdinalIgnoreCase),
            }).ToList();
            if (VersionList.Items.Count > 0)
            {
                var idx = 0;
                for (var i = 0; i < VersionList.Items.Count; i++)
                {
                    if (((VersionRow)VersionList.Items[i]).IsCurrent) { idx = i; break; }
                }
                VersionList.SelectedIndex = idx;
            }
            Loaded += (_, _) =>
            {
                try
                {
                    if (!(Services.InstanceActions.IsManaged(inst)))
                    {
                        HintText.Text = "这是系统安装（" + inst.Source + "），管理器不会改动它；只能查看可用版本。";
                        ApplyBtn.IsEnabled = false;
                    }
                    else HintText.Text = "选中任意版本后点「更新到此版本」，升级和降级都支持。";
                }
                catch { }
            };
        }

        public sealed class VersionRow
        {
            public string Text { get; set; }
            public bool IsCurrent { get; set; }
            public string Tag => IsCurrent ? "当前" : "";
        }

        private void OnDrag(object sender, MouseButtonEventArgs e)
        {
            if (e.LeftButton == MouseButtonState.Pressed) DragMove();
        }

        private void OnClose(object sender, RoutedEventArgs e) => Close();

        private void OnApply(object sender, RoutedEventArgs e)
        {
            if (VersionList.SelectedItem is VersionRow row)
            {
                SelectedVersion = row.Text;
                DialogResult = true;
            }
            Close();
        }
    }
}
