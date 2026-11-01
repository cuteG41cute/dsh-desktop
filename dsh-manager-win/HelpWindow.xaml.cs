using System;
using System.Diagnostics;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using DshManager.Services;

namespace DshManager;

public partial class HelpWindow : Window
{
    public HelpWindow() => InitializeComponent();

    private void OnClose(object sender, RoutedEventArgs e) => Close();

    private void OnOpenRepo(object sender, RoutedEventArgs e)
    {
        try
        {
            Process.Start(new ProcessStartInfo("https://github.com/cuteG41cute/dsh-desktop")
            { UseShellExecute = true });
        }
        catch { }
    }

    private void OnOpenData(object sender, RoutedEventArgs e) => DshHost.OpenFolder(DshManager.Services.DshHost.LogDir);

    private void OnDrag(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Left) return;
        for (var d = e.OriginalSource as DependencyObject; d != null; d = VisualTreeHelper.GetParent(d))
            if (d is System.Windows.Controls.Button) return;
        try { DragMove(); } catch { }
    }
}
