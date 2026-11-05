# 在干净 VM 里跑的验收探针：下载 → 安装 → 启动 → 截屏 + 收集 → 回传宿主
$ErrorActionPreference = 'Continue'
$base = 'http://172.30.16.1:8899'
$out  = Join-Path $env:TEMP 'dshmgr'
New-Item -ItemType Directory -Force $out | Out-Null
try {
  Invoke-WebRequest "$base/DshManager.exe" -OutFile "$out\DshManager.exe" -UseBasicParsing
  Invoke-WebRequest "$base/install-win.ps1" -OutFile "$out\install-win.ps1" -UseBasicParsing
} catch { Write-Host "下载失败: $($_.Exception.Message)"; exit 1 }

Push-Location $out
try { powershell -ExecutionPolicy Bypass -File .\install-win.ps1 | Out-Null } catch {}
Pop-Location

$exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
$installed = Test-Path $exe
if ($installed) { Start-Process $exe; Start-Sleep -Seconds 15 }

# 截屏
$screenB64 = ''
try {
  Add-Type -AssemblyName System.Drawing, System.Windows.Forms
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
  $ms = New-Object System.IO.MemoryStream
  $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
  $screenB64 = [Convert]::ToBase64String($ms.ToArray())
  $g.Dispose(); $bmp.Dispose(); $ms.Dispose()
} catch {}

# 收集信息
$ver = ''
try { $ver = (Get-Item $exe).VersionInfo.FileVersion } catch {}
$uiLog = ''
$p = Join-Path $env:LOCALAPPDATA 'dsh-manager\ui.log'
if (Test-Path $p) { $uiLog = (Get-Content $p -Tail 40 -ErrorAction SilentlyContinue) -join "`n" }
$settings = ''
$ps = Join-Path $env:APPDATA 'dsh-manager\settings.json'
if (Test-Path $ps) { $settings = Get-Content $ps -Raw -ErrorAction SilentlyContinue }
$wins = @()
try { $wins = Get-Process DshManager -ErrorAction SilentlyContinue | Select-Object Id, MainWindowTitle, @{n='ver';e={$_.MainModule.FileVersionInfo.FileVersion}} } catch {}
$dirs = @()
foreach ($d in @((Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager'), (Join-Path $env:LOCALAPPDATA 'dsh-manager'))) {
  if (Test-Path $d) { $dirs += (Get-ChildItem $d -ErrorAction SilentlyContinue | Select-Object -First 12 Name) }
}
$os = (Get-CimInstance Win32_OperatingSystem).Caption
$report = [ordered]@{
  host      = $env:COMPUTERNAME
  os        = $os
  installed = $installed
  version   = $ver
  windows   = $wins
  dirs      = $dirs
  uiLog     = $uiLog
  settings  = $settings
  screen    = $screenB64
} | ConvertTo-Json -Depth 6
try { Invoke-RestMethod -Uri "$base/report" -Method Post -Body $report -ContentType 'application/json' | Out-Null; Write-Host 'REPORT SENT OK' }
catch { Write-Host "回传失败: $($_.Exception.Message)" }
