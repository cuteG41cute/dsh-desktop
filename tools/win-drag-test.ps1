[CmdletBinding()]
param([int]$Dx = -120, [int]$Dy = 0, [string]$ProcessName = "DshManager", [int]$InsetPx = 34, [switch]$Left, [switch]$Top, [switch]$MidX, [switch]$MidY)

# ASCII only: Windows PowerShell 5.1 reads .ps1 as ANSI.
$ErrorActionPreference = 'Stop'

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class DragTest {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, int dx, int dy, uint d, IntPtr e);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    public static void Down() { mouse_event(0x0002, 0, 0, 0, IntPtr.Zero); }
    public static void Up()   { mouse_event(0x0004, 0, 0, 0, IntPtr.Zero); }
    public static void Move(int x, int y) { SetCursorPos(x, y); }
}
"@

[DragTest]::SetProcessDPIAware() | Out-Null

# 直接拿进程的主窗口句柄，避免按标题前缀误匹配到别的窗口（本机还有个「WebUI 启动器」）
$proc = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) { throw "no window for process $ProcessName" }
$h = $proc.MainWindowHandle
Write-Host ("hwnd=0x{0:X} pid={1} title={2}" -f [int64]$h, $proc.Id, $proc.MainWindowTitle)

[void][DragTest]::ShowWindow($h, 9)
$topmost = New-Object IntPtr -ArgumentList (-1)
[void][DragTest]::SetWindowPos($h, $topmost, 0, 0, 0, 0, 0x0003)
[void][DragTest]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 500
$fg = [DragTest]::GetForegroundWindow()
Write-Host ("foreground is target: {0}" -f ($fg -eq $h))

$r = New-Object DragTest+RECT
[void][DragTest]::GetWindowRect($h, [ref]$r)
Write-Host ("before: ({0},{1})-({2},{3})  size {4}x{5}" -f $r.Left, $r.Top, $r.Right, $r.Bottom,
    ($r.Right - $r.Left), ($r.Bottom - $r.Top))

if ($MidX) { $x = [int](($r.Left + $r.Right) / 2) } elseif ($Left) { $x = $r.Left + $InsetPx } else { $x = $r.Right - $InsetPx }
if ($MidY) { $y = [int](($r.Top + $r.Bottom) / 2) } elseif ($Top) { $y = $r.Top + $InsetPx } else { $y = $r.Bottom - $InsetPx }
Write-Host "grip at ($x,$y), drag delta ($Dx,$Dy)"

[DragTest]::Move($x, $y)
Start-Sleep -Milliseconds 350
[DragTest]::Down()
Start-Sleep -Milliseconds 250
for ($i = 1; $i -le 8; $i++) {
    [DragTest]::Move($x + [int]($Dx * $i / 8), $y + [int]($Dy * $i / 8))
    Start-Sleep -Milliseconds 70
}
Start-Sleep -Milliseconds 150
[DragTest]::Up()
Start-Sleep -Milliseconds 700

[void][DragTest]::GetWindowRect($h, [ref]$r)
$notTop = New-Object IntPtr -ArgumentList (-2)
[void][DragTest]::SetWindowPos($h, $notTop, 0, 0, 0, 0, 0x0003)
Write-Host ("after:  ({0},{1})-({2},{3})  size {4}x{5}" -f $r.Left, $r.Top, $r.Right, $r.Bottom,
    ($r.Right - $r.Left), ($r.Bottom - $r.Top))
