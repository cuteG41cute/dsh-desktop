$ErrorActionPreference = 'Continue'
$log = 'C:\Users\User\probe2.out.txt'
"session=" + [System.Diagnostics.Process]::GetCurrentProcess().SessionId | Out-File $log -Encoding UTF8
"interactive=" + [Environment]::UserInteractive | Out-File $log -Append -Encoding UTF8
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
try {
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  "screen=" + $b.Width + "x" + $b.Height | Out-File $log -Append -Encoding UTF8
  $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
  $bmp.Save('C:\Users\User\shot.png', [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  "shot=ok" | Out-File $log -Append -Encoding UTF8
} catch { "shot failed: " + $_.Exception.Message | Out-File $log -Append -Encoding UTF8 }
$p = Get-Process DshManager -ErrorAction SilentlyContinue
"proc=" + (@($p).Count) | Out-File $log -Append -Encoding UTF8
foreach ($x in @($p)) { "  pid=" + $x.Id + " session=" + $x.SessionId + " title=" + $x.MainWindowTitle | Out-File $log -Append -Encoding UTF8 }
