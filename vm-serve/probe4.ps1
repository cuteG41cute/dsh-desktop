$ErrorActionPreference = 'Continue'
$log = 'C:\Users\User\probe4.out.txt'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing, System.Windows.Forms
"start" | Set-Content $log -Encoding ASCII
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, 'DeepSeek Harness 管理器')
$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
if (-not $win) { "main window not found" | Add-Content $log; exit }
"main ok" | Add-Content $log
# 找「新建实例」按钮
$btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, '新建实例')
$btn = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
if (-not $btn) { "new button not found" | Add-Content $log; exit }
$btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Seconds 2
"clicked" | Add-Content $log
# 截屏
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$bmp.Save('C:\Users\User\shot4.png', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"shot ok" | Add-Content $log
# 列出对话框里的按钮，确认窗口内容
$dlgCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, '新建实例')
$dlg = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $dlgCond)
if ($dlg) {
  "dialog found" | Add-Content $log
  $all = $dlg.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
  $names = @()
  foreach ($e in $all) { $n = $e.Current.Name; if ($n) { $names += ($e.Current.ControlType.ProgrammaticName + ':' + $n) } }
  ($names | Select-Object -First 30) | Add-Content $log
} else { "dialog not found" | Add-Content $log }
