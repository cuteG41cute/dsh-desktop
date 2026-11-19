using System;
using System.Globalization;
using System.Windows;

namespace DshManager.ViewModels;

/// <summary>备份历史行。</summary>
public sealed class BackupRowVm
{
    public string Title { get; init; } = "";
    public string Meta { get; init; } = "";
    public string StatusText { get; init; } = "成功";
    public string File { get; init; } = "";
}

/// <summary>项目列表行（UI 绑定用）。</summary>
public sealed class ProjectRowVm
{
    public string Id { get; init; } = "";
    public string Title { get; init; } = "";
    public string Path { get; init; } = "";
    public string BadgeText { get; init; } = "未备份";
    public string MetaLine { get; init; } = "";
    public string BackupLine { get; init; } = "";
    public string HandoffText { get; init; } = "";
    public Visibility HandoffVisibility { get; init; } = Visibility.Collapsed;
    public string SearchKey { get; init; } = "";

    public static string Relative(DateTime? at)
    {
        if (at == null) return "未知";
        var span = DateTime.Now - at.Value;
        if (span.TotalMinutes < 1) return "刚刚";
        if (span.TotalMinutes < 60) return $"{(int)span.TotalMinutes} 分钟前";
        if (span.TotalHours < 24) return $"{(int)span.TotalHours} 小时前";
        if (span.TotalDays < 30) return $"{(int)span.TotalDays} 天前";
        return at.Value.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    }

    public static string Size(long bytes)
    {
        if (bytes >= 1024L * 1024 * 1024) return (bytes / 1024.0 / 1024 / 1024).ToString("0.##") + " GB";
        if (bytes >= 1024 * 1024) return (bytes / 1024.0 / 1024).ToString("0.#") + " MB";
        if (bytes >= 1024) return (bytes / 1024.0).ToString("0") + " KB";
        return bytes + " B";
    }
}
