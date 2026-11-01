[CmdletBinding()]
param([string]$TitleLike = "DeepSeek Harness", [switch]$Exact, [int]$FromRight = 51, [int]$FromTop = 19,
      [switch]$DoubleClick, [switch]$NoTopmost)

# ASCII only: Windows PowerShell 5.1 reads .ps1 as ANSI.
# Synthetic click on a window found by title (the session window has a WebView2 child,
# so the click point must be inside the WPF toolbar area, i.e. the top 38px).
$ErrorActionPreference = 'Stop'

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinClick {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, int dx, int dy, uint d, IntPtr e);
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int max);
    public static void Click(int x, int y) {
        SetCursorPos(x, y); System.Threading.Thread.Sleep(180);
        mouse_event(0x0002, 0, 0, 0, IntPtr.Zero); System.Threading.Thread.Sleep(100);
        mouse_event(0x0004, 0, 0, 0, IntPtr.Zero);
    }
    public static void DoubleClick(int x, int y) {
        SetCursorPos(x, y); System.Threading.Thread.Sleep(180);
        mouse_event(0x0002, 0, 0, 0, IntPtr.Zero); System.Threading.Thread.Sleep(60);
        mouse_event(0x0004, 0, 0, 0, IntPtr.Zero); System.Threading.Thread.Sleep(90);
        mouse_event(0x0002, 0, 0, 0, IntPtr.Zero); System.Threading.Thread.Sleep(60);
        mouse_event(0x0004, 0, 0, 0, IntPtr.Zero);
    }
    public static IntPtr Find(string like, bool exact) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h, l) => {
            if (!IsWindowVisible(h)) return true;
            var sb = new StringBuilder(512);
            GetWindowTextW(h, sb, 512);
            var t = sb.ToString();
            var hit = exact ? string.Equals(t, like, StringComparison.OrdinalIgnoreCase)
                            : t.IndexOf(like, StringComparison.OrdinalIgnoreCase) >= 0;
            if (!hit) return true;
            var r = new RECT();
            if (!GetWindowRect(h, out r)) return true;
            if (r.Right - r.Left < 200 || r.Bottom - r.Top < 150) return true;
            found = h;
            return false;
        }, IntPtr.Zero);
        return found;
    }
}
"@

$h = [WinClick]::Find($TitleLike, [bool]$Exact)
if ($h -eq [IntPtr]::Zero) { throw "no visible window matching '$TitleLike'" }

$top = New-Object IntPtr -ArgumentList (-1)
$notTop = New-Object IntPtr -ArgumentList (-2)
if (-not $NoTopmost) {
    [void][WinClick]::SetWindowPos($h, $top, 0, 0, 0, 0, 0x0003)
    Start-Sleep -Milliseconds 500
}

$r = New-Object WinClick+RECT
[void][WinClick]::GetWindowRect($h, [ref]$r)
$cx = $r.Right - $FromRight
$cy = $r.Top + $FromTop
Write-Host ("hwnd=0x{0:X} rect=({1},{2})-({3},{4}) click=({5},{6})" -f [int64]$h, $r.Left, $r.Top, $r.Right, $r.Bottom, $cx, $cy)

if ($DoubleClick) { [WinClick]::DoubleClick($cx, $cy) } else { [WinClick]::Click($cx, $cy) }
Start-Sleep -Milliseconds 900

[void][WinClick]::GetWindowRect($h, [ref]$r)
if (-not $NoTopmost) { [void][WinClick]::SetWindowPos($h, $notTop, 0, 0, 0, 0, 0x0003) }
Write-Host ("after: rect=({0},{1})-({2},{3}) size {4}x{5}" -f $r.Left, $r.Top, $r.Right, $r.Bottom,
    ($r.Right - $r.Left), ($r.Bottom - $r.Top))
