$ErrorActionPreference = 'Continue'
$log = 'C:\Users\User\act.out.txt'
Set-Content $log -Value 'start' -Encoding ASCII
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices; public class Dpi2{[DllImport("user32.dll")]public static extern bool SetProcessDPIAware();}'
[Dpi2]::SetProcessDPIAware() | Out-Null
Add-Type @"
using System;using System.Text;using System.Runtime.InteropServices;
public class A{
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
 [DllImport("kernel32.dll")]public static extern IntPtr GetConsoleWindow();
 [DllImport("user32.dll")]public static extern void mouse_event(uint f,uint dx,uint dy,uint d,IntPtr e);
 public struct RECT{public int L,T,R,B;}
 public static IntPtr Find(int pid){
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
  SetCursorPos(x,y); System.Threading.Thread.Sleep(140);
  mouse_event(0x0002,0,0,0,IntPtr.Zero); System.Threading.Thread.Sleep(80);
  mouse_event(0x0004,0,0,0,IntPtr.Zero);}
}
"@
$mySess = (Get-Process -Id $PID).SessionId
$p = Get-Process DshManager -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $mySess } | Select-Object -First 1
if (-not $p) { Add-Content $log 'no manager in session 1'; exit }
$h = [A]::Find($p.Id)
$cw = [A]::GetConsoleWindow()
if ($cw -ne [IntPtr]::Zero) { [void][A]::ShowWindow($cw, 0) }
Add-Content $log ("hwnd=" + $h)
$rect = New-Object A+RECT

function Get-Rect {
  [void][A]::GetWindowRect($h, [ref]$rect)
  return $rect
}
function Shot([string]$name) {
  [void][A]::SetForegroundWindow($h)
  Start-Sleep -Milliseconds 300
  $r = Get-Rect
  $w = $r.R - $r.L; $ht = $r.B - $r.T
  if ($w -le 0 -or $ht -le 0) { Add-Content $log "shot skip (bad rect)"; return }
  $bmp = New-Object System.Drawing.Bitmap($w, $ht)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size($w, $ht)))
  $path = 'C:\Users\User\' + $name + '.png'
  $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Add-Content $log ("shot " + $name + " " + $w + "x" + $ht)
}

$actions = Get-Content 'C:\Users\User\actions.txt' -ErrorAction SilentlyContinue
foreach ($line in $actions) {
  $t = $line.Trim()
  if ($t.Length -eq 0 -or $t.StartsWith('#')) { continue }
  $parts = $t -split '\s+'
  switch ($parts[0]) {
    'win' {
      [void][A]::ShowWindow($h, 9)
      [void][A]::SetWindowPos($h, [IntPtr]::Zero, [int]$parts[1], [int]$parts[2], [int]$parts[3], [int]$parts[4], 0x0004)
      [void][A]::SetForegroundWindow($h)
      Start-Sleep -Milliseconds 700
      $r = Get-Rect
      Add-Content $log ("win -> " + $r.L + "," + $r.T + "," + $r.R + "," + $r.B)
    }
    'click' {
      $x = [int]$parts[1]; $y = [int]$parts[2]
      [A]::Click($x, $y); Start-Sleep -Milliseconds 450
      Add-Content $log ("click " + $x + "," + $y)
    }
    'dclick' {
      $x = [int]$parts[1]; $y = [int]$parts[2]
      [A]::Click($x, $y); Start-Sleep -Milliseconds 120; [A]::Click($x, $y)
      Start-Sleep -Milliseconds 400
      Add-Content $log ("dclick " + $x + "," + $y)
    }
    'type' {
      $text = ($parts[1..($parts.Length-1)] -join ' ')
      [System.Windows.Forms.SendKeys]::SendWait($text)
      Start-Sleep -Milliseconds 300
      Add-Content $log ("type " + $text)
    }
    'uia' {
      $target = ($parts[1..($parts.Length-1)] -join ' ')
      try {
        Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
        $root = [System.Windows.Automation.AutomationElement]::RootElement
        $byName = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $target)
        $byType = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
        $cond = New-Object System.Windows.Automation.AndCondition($byName, $byType)
        $el = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
        if ($el) {
          $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
          Add-Content $log ("uia invoked " + $target)
        } else { Add-Content $log ("uia not found " + $target) }
      } catch { Add-Content $log ("uia failed " + $target + " : " + $_.Exception.Message) }
      Start-Sleep -Milliseconds 700
    }
    'uiaid' {
      $id = $parts[1]
      try {
        Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
        $root = [System.Windows.Automation.AutomationElement]::RootElement
        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
        $el = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
        if ($el) {
          $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
          Add-Content $log ("uiaid invoked " + $id)
        } else { Add-Content $log ("uiaid not found " + $id) }
      } catch { Add-Content $log ("uiaid failed " + $id + " : " + $_.Exception.Message) }
      Start-Sleep -Milliseconds 700
    }
    'sleep' { Start-Sleep -Milliseconds ([int]$parts[1]) }
    'shot' { Shot $parts[1] }
    'shotfull' {
      $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
      $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
      $bmp.Save(('C:\Users\User\' + $parts[1] + '.png'), [System.Drawing.Imaging.ImageFormat]::Png)
      $g.Dispose(); $bmp.Dispose()
      Add-Content $log ("shotfull " + $parts[1])
    }
    default { Add-Content $log ("skip " + $t) }
  }
}
Add-Content $log 'done'
