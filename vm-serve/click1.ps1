$ErrorActionPreference = 'Continue'
$log = 'C:\Users\User\click1.out.txt'
"start" | Set-Content $log -Encoding ASCII
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices; public class Dpi{[DllImport("user32.dll")]public static extern bool SetProcessDPIAware();}'
[Dpi]::SetProcessDPIAware() | Out-Null
Add-Type @"
using System;using System.Text;using System.Runtime.InteropServices;
public class X{
 [DllImport("user32.dll")]public static extern bool EnumWindows(EnumProc cb,IntPtr l);
 public delegate bool EnumProc(IntPtr h,IntPtr l);
 [DllImport("user32.dll")]public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll")]public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)]public static extern int GetWindowTextW(IntPtr h,StringBuilder s,int m);
 [DllImport("user32.dll")]public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")]public static extern bool SetWindowPos(IntPtr h,IntPtr a,int x,int y,int cx,int cy,uint f);
 [DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")]public static extern bool ShowWindow(IntPtr h,int c);
 [DllImport("user32.dll")]public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")]public static extern void mouse_event(uint f,uint dx,uint dy,uint d,IntPtr e);
 public struct RECT{public int L,T,R,B;}
 public static IntPtr FindByPid(int pid){
  IntPtr found=IntPtr.Zero;
  EnumWindows((h,l)=>{
    uint p;GetWindowThreadProcessId(h,out p);
    if(p==(uint)pid && IsWindowVisible(h)){
      var t=new StringBuilder(256);GetWindowTextW(h,t,256);
      if(t.Length>0){found=h;return false;}
    }
    return true;},IntPtr.Zero);
  return found;}
 public static void Click(int x,int y){
  SetCursorPos(x,y); System.Threading.Thread.Sleep(150);
  mouse_event(0x0002,0,0,0,IntPtr.Zero); System.Threading.Thread.Sleep(90);
  mouse_event(0x0004,0,0,0,IntPtr.Zero);}
}
"@
$p = Get-Process DshManager -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 1 } | Select-Object -First 1
if (-not $p) { "no manager in session 1" | Add-Content $log; exit }
"pid=" + $p.Id | Add-Content $log
$h = [X]::FindByPid($p.Id)
"hwnd=" + $h | Add-Content $log
if ($h -eq [IntPtr]::Zero) { exit }
[void][X]::ShowWindow($h, 9)
[void][X]::SetWindowPos($h, [IntPtr]::Zero, 40, 40, 900, 600, 0x0004)
[void][X]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 900
$r = New-Object X+RECT
[void][X]::GetWindowRect($h, [ref]$r)
"rect=$($r.L),$($r.T),$($r.R),$($r.B)" | Add-Content $log

$w = $r.R - $r.L
$ht = $r.B - $r.T
$x = $r.L + 302
$y = $r.T + 367
"click=$x,$y size=$w x $ht" | Add-Content $log
[X]::Click($x, $y)
Start-Sleep -Milliseconds 500
[X]::Click($x, $y)
Start-Sleep -Seconds 3

$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size($w, $ht)))
$bmp.Save('C:\Users\User\click1.png', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"shot ok" | Add-Content $log
