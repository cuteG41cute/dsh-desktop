[CmdletBinding()]
param([int]$Dx = -120, [int]$Dy = 0, [string]$TitleLike = "DeepSeek Harness", [string]$NotLike = "",
      [switch]$Exact, [int]$InsetPx = 34, [switch]$Left, [switch]$Top, [switch]$MidX, [switch]$MidY)

# ASCII only: Windows PowerShell 5.1 reads .ps1 as ANSI.
# Same synthetic drag as win-drag-test.ps1, but the target window is looked up by
# title (EnumWindows) instead of Process.MainWindowHandle -- needed for the session
# window, whose owner process also has a (hidden) manager window.
$ErrorActionPreference = 'Stop'

Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class DragWin {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, int dx, int dy, uint d, IntPtr e);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int max);
    public static void Down() { mouse_event(0x0002, 0, 0, 0, IntPtr.Zero); }
    public static void Up()   { mouse_event(0x0004, 0, 0, 0, IntPtr.Zero); }
    public static void Move(int x, int y) { SetCursorPos(x, y); }

    public static IntPtr Find(string like, string notLike, bool exact) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h, l) => {
            if (!IsWindowVisible(h)) return true;
            var sb = new StringBuilder(512);
            GetWindowTextW(h, sb, 512);
            var t = sb.ToString();
            var hit = exact ? string.Equals(t, like, StringComparison.OrdinalIgnoreCase)
                            : t.IndexOf(like, StringComparison.OrdinalIgnoreCase) >= 0;
            if (!hit) return true;
            if (notLike.Length > 0 && t.IndexOf(notLike, StringComparison.OrdinalIgnoreCase) >= 0) return true;
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

[DragWin]::SetProcessDPIAware() | Out-Null

$h = [DragWin]::Find($TitleLike, $NotLike, [bool]$Exact)
if ($h -eq [IntPtr]::Zero) { throw "no visible window matching '$TitleLike'" }

[void][DragWin]::ShowWindow($h, 9)
$topmost = New-Object IntPtr -ArgumentList (-1)
[void][DragWin]::SetWindowPos($h, $topmost, 0, 0, 0, 0, 0x0003)
[void][DragWin]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 500
$fg = [DragWin]::GetForegroundWindow()
Write-Host ("hwnd=0x{0:X} foreground is target: {1}" -f [int64]$h, ($fg -eq $h))

$r = New-Object DragWin+RECT
[void][DragWin]::GetWindowRect($h, [ref]$r)
Write-Host ("before: ({0},{1})-({2},{3})  size {4}x{5}" -f $r.Left, $r.Top, $r.Right, $r.Bottom,
    ($r.Right - $r.Left), ($r.Bottom - $r.Top))

if ($MidX) { $x = [int](($r.Left + $r.Right) / 2) } elseif ($Left) { $x = $r.Left + $InsetPx } else { $x = $r.Right - $InsetPx }
if ($MidY) { $y = [int](($r.Top + $r.Bottom) / 2) } elseif ($Top) { $y = $r.Top + $InsetPx } else { $y = $r.Bottom - $InsetPx }
Write-Host "grip at ($x,$y), drag delta ($Dx,$Dy)"

[DragWin]::Move($x, $y)
Start-Sleep -Milliseconds 350
[DragWin]::Down()
Start-Sleep -Milliseconds 250
for ($i = 1; $i -le 8; $i++) {
    [DragWin]::Move($x + [int]($Dx * $i / 8), $y + [int]($Dy * $i / 8))
    Start-Sleep -Milliseconds 70
}
Start-Sleep -Milliseconds 150
[DragWin]::Up()
Start-Sleep -Milliseconds 700

[void][DragWin]::GetWindowRect($h, [ref]$r)
$notTop = New-Object IntPtr -ArgumentList (-2)
[void][DragWin]::SetWindowPos($h, $notTop, 0, 0, 0, 0, 0x0003)
Write-Host ("after:  ({0},{1})-({2},{3})  size {4}x{5}" -f $r.Left, $r.Top, $r.Right, $r.Bottom,
    ($r.Right - $r.Left), ($r.Bottom - $r.Top))
