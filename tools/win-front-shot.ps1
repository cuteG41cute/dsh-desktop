[CmdletBinding()]
param([string]$Out = "vm-shots\front.png", [string]$ProcessName = "DshManager")

# Bring our window to front (topmost for a moment) and grab the whole desktop.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Front {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[Front]::SetProcessDPIAware() | Out-Null
$proc = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) { throw "no window for $ProcessName" }
$h = $proc.MainWindowHandle
$top = New-Object IntPtr -ArgumentList (-1)
$notTop = New-Object IntPtr -ArgumentList (-2)
[void][Front]::SetWindowPos($h, $top, 0, 0, 0, 0, 0x0003)
[void][Front]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 700

$r = New-Object Front+RECT
[void][Front]::GetWindowRect($h, [ref]$r)
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.X, $b.Y, 0, 0, (New-Object System.Drawing.Size $b.Width, $b.Height))
$g.Dispose()
$full = [System.IO.Path]::GetFullPath($Out)
$bmp.Save($full, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
[void][Front]::SetWindowPos($h, $notTop, 0, 0, 0, 0, 0x0003)
Write-Host ("saved {0}   window rect=({1},{2})-({3},{4})" -f $full, $r.Left, $r.Top, $r.Right, $r.Bottom)
