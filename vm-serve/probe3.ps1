$ErrorActionPreference = 'Continue'
$log = 'C:\Users\User\probe3.out.txt'
"start" | Out-File $log -Encoding UTF8
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @"
using System;using System.Text;using System.Runtime.InteropServices;
public class W{
 [DllImport("user32.dll")]public static extern bool EnumWindows(EnumProc cb,IntPtr l);
 public delegate bool EnumProc(IntPtr h,IntPtr l);
 [DllImport("user32.dll")]public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)]public static extern int GetWindowTextW(IntPtr h,StringBuilder s,int m);
 [DllImport("user32.dll")]public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")]public static extern bool SetWindowPos(IntPtr h,IntPtr a,int x,int y,int cx,int cy,uint f);
 [DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")]public static extern bool ShowWindow(IntPtr h,int c);
 public struct RECT{public int L,T,R,B;}
 public static IntPtr Find(int pid){IntPtr r=IntPtr.Zero;
  EnumWindows((h,l)=>{uint p;GetWindowThreadProcessId(h,out p);if(p!=(uint)pid)return true;
   var t=new StringBuilder(256);GetWindowTextW(h,t,256);if(t.ToString().Contains("管理器")){r=h;return false;}return true;},IntPtr.Zero);
  return r;}
}
"@
$p = Get-Process DshManager -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { "no manager" | Out-File $log -Append; exit }
$h = [W]::Find($p.Id)
"hwnd=$h" | Out-File $log -Append
[void][W]::ShowWindow($h, 9)
[void][W]::SetWindowPos($h, [IntPtr]::Zero, 40, 40, 900, 600, 0x0004)
[void][W]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 800
$r = New-Object W+RECT
[void][W]::GetWindowRect($h, [ref]$r)
"rect=$($r.L),$($r.T),$($r.R),$($r.B)" | Out-File $log -Append
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$bmp.Save('C:\Users\User\shot3.png', [System.Drawing.Imaging.ImageFormat]::Png)
foreach ($pt in @(@($r.L+1,$r.T+1), @($r.L+4,$r.T+4), @($r.L+10,$r.T+10), @($r.L+1,$r.B-2), @($r.R-2,$r.T+1))) {
  $px = $bmp.GetPixel($pt[0], $pt[1])
  "px($($pt[0]),$($pt[1]))=#$($px.R.ToString('X2'))$($px.G.ToString('X2'))$($px.B.ToString('X2'))" | Out-File $log -Append
}
$g.Dispose(); $bmp.Dispose()
"done" | Out-File $log -Append
