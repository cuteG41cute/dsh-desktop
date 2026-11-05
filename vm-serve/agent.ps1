$ErrorActionPreference = 'Continue'
# 常驻代理：轮询 C:\Users\User\req.txt，执行动作，把结果写到 C:\Users\User\res.txt
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices; public class DpiA{[DllImport("user32.dll")]public static extern bool SetProcessDPIAware();}'
[DpiA]::SetProcessDPIAware() | Out-Null
Add-Type @"
using System;using System.Text;using System.Runtime.InteropServices;
public class AG{
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
 [DllImport("kernel32.dll")]public static extern IntPtr GetConsoleWindow();
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
  SetCursorPos(x,y); System.Threading.Thread.Sleep(130);
  mouse_event(0x0002,0,0,0,IntPtr.Zero); System.Threading.Thread.Sleep(80);
  mouse_event(0x0004,0,0,0,IntPtr.Zero);}
}
"@
$cw = [AG]::GetConsoleWindow()
if ($cw -ne [IntPtr]::Zero) { [void][AG]::ShowWindow($cw, 0) }

$reqFile = 'C:\Users\User\req.txt'
$resFile = 'C:\Users\User\res.txt'
$mySess  = (Get-Process -Id $PID).SessionId
Set-Content 'C:\Users\User\agent.alive' 'up' -Encoding ASCII

while ($true) {
    if (Test-Path $reqFile) {
        $lines = @()
        try { $lines = Get-Content $reqFile } catch {}
        Remove-Item $reqFile -Force -ErrorAction SilentlyContinue
        $out = New-Object System.Collections.Generic.List[string]
        $h = [IntPtr]::Zero
        $rect = New-Object AG+RECT
        $mgrPid = 0

        foreach ($line in $lines) {
            $t = $line.Trim()
            if ($t.Length -eq 0 -or $t.StartsWith('#')) { continue }
            $p = $t -split '\s+'
            switch ($p[0]) {
                'pid' {
                    $proc = Get-Process DshManager -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $mySess } | Select-Object -First 1
                    if ($proc) { $mgrPid = $proc.Id; $h = [AG]::Find($proc.Id) }
                    $out.Add('pid=' + $mgrPid + ' hwnd=' + $h)
                }
                'win' {
                    [void][AG]::ShowWindow($h, 9)
                    [void][AG]::SetWindowPos($h, [IntPtr]::Zero, [int]$p[1], [int]$p[2], [int]$p[3], [int]$p[4], 0x0004)
                    [void][AG]::SetForegroundWindow($h)
                    Start-Sleep -Milliseconds 700
                    [void][AG]::GetWindowRect($h, [ref]$rect)
                    $out.Add('win=' + $rect.L + ',' + $rect.T + ',' + $rect.R + ',' + $rect.B)
                }
                'click' { [AG]::Click([int]$p[1], [int]$p[2]); Start-Sleep -Milliseconds 450; $out.Add('click ' + $p[1] + ',' + $p[2]) }
                'dclick' {
                    [AG]::Click([int]$p[1], [int]$p[2]); Start-Sleep -Milliseconds 120; [AG]::Click([int]$p[1], [int]$p[2])
                    Start-Sleep -Milliseconds 400; $out.Add('dclick ' + $p[1] + ',' + $p[2])
                }
                'type' { $txt = ($p[1..($p.Length-1)] -join ' '); [System.Windows.Forms.SendKeys]::SendWait($txt); Start-Sleep -Milliseconds 300; $out.Add('type ' + $txt) }
                'wheel' {
                    $delta = [int]$p[1]        # 正数=向上滚，负数=向下滚
                    [void][AG]::SetCursorPos([int]$p[2], [int]$p[3])
                    Start-Sleep -Milliseconds 120
                    for ($k = 0; $k -lt [math]::Abs($delta); $k++) {
                        $d = [uint32](120 * [math]::Sign($delta))
                        $dw = [UIntPtr]::new($d)
                        [AG]::mouse_event(0x0800, 0, 0, $d, [IntPtr]::Zero)
                        Start-Sleep -Milliseconds 60
                    }
                    Start-Sleep -Milliseconds 300
                    $out.Add('wheel ' + $delta)
                }
                'res' {
                    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
                    $out.Add('res=' + $b.Width + 'x' + $b.Height)
                }
                'setval' {
                    $id = $p[1]
                    $val = ($p[2..($p.Length-1)] -join ' ')
                    try {
                        Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
                        $root = [System.Windows.Automation.AutomationElement]::RootElement
                        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
                        $el = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
                        if ($el) {
                            $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($val)
                            $out.Add('setval ' + $id + ' = ' + $val)
                        } else { $out.Add('setval notfound ' + $id) }
                    } catch { $out.Add('setval err ' + $_.Exception.Message) }
                    Start-Sleep -Milliseconds 500
                }
                'drag' {
                    $x1=[int]$p[1]; $y1=[int]$p[2]; $x2=[int]$p[3]; $y2=[int]$p[4]
                    [AG]::SetCursorPos($x1,$y1); Start-Sleep -Milliseconds 200
                    [AG]::mouse_event(0x0002,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 200
                    $steps = 12
                    for ($i=1; $i -le $steps; $i++) {
                        $nx = [int]($x1 + ($x2-$x1)*$i/$steps)
                        $ny = [int]($y1 + ($y2-$y1)*$i/$steps)
                        [AG]::SetCursorPos($nx,$ny); Start-Sleep -Milliseconds 40
                    }
                    Start-Sleep -Milliseconds 150
                    [AG]::mouse_event(0x0004,0,0,0,[IntPtr]::Zero)
                    Start-Sleep -Milliseconds 600
                    $out.Add('drag ' + $x1 + ',' + $y1 + ' -> ' + $x2 + ',' + $y2)
                }
                'sleep' { Start-Sleep -Milliseconds ([int]$p[1]) }
                'focus' { if ($h -ne [IntPtr]::Zero) { [void][AG]::SetForegroundWindow($h); Start-Sleep -Milliseconds 400; $out.Add('focus ok') } }
                'uiaid' {
                    try {
                        Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
                        $root = [System.Windows.Automation.AutomationElement]::RootElement
                        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $p[1])
                        $el = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
                        if ($el) {
                            try { $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
                            catch { try { $el.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Toggle() } catch { } }
                            $out.Add('uiaid ' + $p[1] + ' ok')
                        } else { $out.Add('uiaid ' + $p[1] + ' notfound') }
                    } catch { $out.Add('uiaid err ' + $_.Exception.Message) }
                    Start-Sleep -Milliseconds 700
                }
                'shot' {
                    [void][AG]::SetForegroundWindow($h)
                    Start-Sleep -Milliseconds 300
                    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
                    $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
                    $g = [System.Drawing.Graphics]::FromImage($bmp)
                    $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
                    $bmp.Save(('C:\Users\User\' + $p[1] + '.png'), [System.Drawing.Imaging.ImageFormat]::Png)
                    $g.Dispose(); $bmp.Dispose()
                    $out.Add('shot ' + $p[1])
                }
                'kill' {
                    Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }
                    Start-Sleep -Seconds 2
                    $out.Add('killed')
                }
                'start' {
                    $exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
                    Start-Process $exe
                    Start-Sleep -Seconds 10
                    $proc = Get-Process DshManager -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $mySess } | Select-Object -First 1
                    if ($proc) { $mgrPid = $proc.Id; $h = [AG]::Find($proc.Id) }
                    $out.Add('started pid=' + $mgrPid + ' hwnd=' + $h)
                }
                'del' {
                    try { Remove-Item $p[1] -Recurse -Force -ErrorAction Stop; $out.Add('del ok ' + $p[1]) } catch { $out.Add('del fail ' + $_.Exception.Message) }
                }
                'ls' {
                    try { $out.Add('ls ' + $p[1] + ' => ' + (@(Get-ChildItem $p[1] -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ',')) } catch { $out.Add('ls err') }
                }
                'ps' {
                    $out.Add('ps ' + (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match $p[1] } | ForEach-Object { "$($_.ProcessName):$($_.Id)" }) -join ','))
                }
                default { $out.Add('skip ' + $t) }
            }
        }
        Set-Content $resFile ($out -join "`r`n") -Encoding UTF8
    }
    Start-Sleep -Milliseconds 600
}
