# Capture a window by title to a PNG (Windows).
#
#   powershell -File tools\win-shot.ps1 -Out shot.png [-Title "DeepSeek Harness"] [-HideOthers]
#
# 说明：刻意**不**调用 SetProcessDPIAware()。在高 DPI（本机 200%）下，先声明 DPI 感知
# 再取窗口矩形/屏幕尺寸会拿到互相矛盾的数值（实测出现过 9,046,336 这种垃圾高度）。
# 保持进程 DPI 不感知，GetWindowRect 与 CopyFromScreen 都在同一套虚拟化坐标里，
# 拍出来的图是 DIP 尺寸（本机 1280×812），够做像素比对。
[CmdletBinding()]
param(
    [string]$Out = "win-shot.png",
    [string]$Title = "DeepSeek Harness",
    [int]$Pad = 0,
    [switch]$HideOthers
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinShot {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindowW(string cls, string title);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int idx);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int max);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int max);
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);

    public static IntPtr FindByPrefix(string prefix) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h, l) => {
            var sb = new StringBuilder(512);
            GetWindowTextW(h, sb, 512);
            if (sb.Length > 0 && sb.ToString().StartsWith(prefix)) { found = h; return false; }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    public static System.Collections.Generic.List<IntPtr> OtherVisibleTops(IntPtr skip) {
        var list = new System.Collections.Generic.List<IntPtr>();
        EnumWindows((h, l) => {
            if (h == skip || !IsWindowVisible(h)) return true;
            var cls = new StringBuilder(256);
            GetClassNameW(h, cls, 256);
            var c = cls.ToString();
            if (c == "Shell_TrayWnd" || c == "Shell_SecondaryTrayWnd" || c == "Progman" || c == "WorkerW") return true;
            var t = new StringBuilder(512);
            GetWindowTextW(h, t, 512);
            if (t.Length == 0) return true;
            list.Add(h);
            return true;
        }, IntPtr.Zero);
        return list;
    }
}
"@

$hwnd = [WinShot]::FindWindowW($null, $Title)
if ($hwnd -eq [IntPtr]::Zero) { $hwnd = [WinShot]::FindByPrefix($Title) }
if ($hwnd -eq [IntPtr]::Zero) { throw "window not found: $Title" }

# 本机是 200% 缩放：DPI 不感知时拿到的是 DIP（1280×812），截图会变成"半个窗口放大"。
# 所以这里声明 DPI 感知，全部用物理像素；只信窗口矩形，不去问 WinForms 的屏幕尺寸
# （那个在 DPI 感知进程里会给出 526300 这种垃圾值）。
[WinShot]::SetProcessDPIAware() | Out-Null

[WinShot]::ShowWindow($hwnd, 9) | Out-Null       # SW_RESTORE
[WinShot]::SetForegroundWindow($hwnd) | Out-Null
$hidden = @()
if ($HideOthers) {
    $hidden = [WinShot]::OtherVisibleTops($hwnd)
    foreach ($h in $hidden) { [WinShot]::ShowWindow($h, 6) | Out-Null }   # SW_MINIMIZE
}
Start-Sleep -Milliseconds 800

$r = New-Object WinShot+RECT
[WinShot]::GetWindowRect($hwnd, [ref]$r) | Out-Null
$x = $r.Left - $Pad
$y = $r.Top - $Pad
$w = ($r.Right - $r.Left) + 2 * $Pad
$h = ($r.Bottom - $r.Top) + 2 * $Pad
if ($w -le 0 -or $h -le 0 -or $w -gt 20000 -or $h -gt 20000) {
    $x = 0; $y = 0
    $w = [WinShot]::GetSystemMetrics(0)
    $h = [WinShot]::GetSystemMetrics(1)
}

$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size $w, $h))
$g.Dispose()

foreach ($h2 in $hidden) { [WinShot]::ShowWindow($h2, 9) | Out-Null }   # SW_RESTORE

$full = [System.IO.Path]::GetFullPath($Out)
$bmp.Save($full, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host "saved $full ($w x $h) from ($x,$y)"
