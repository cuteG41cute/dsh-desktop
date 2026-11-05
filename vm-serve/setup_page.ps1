$root = 'C:\Users\User\AppData\Local\dsh-manager\instances\svctest'
$node = Join-Path $root 'node\node.exe'

# 1) 打开 WebPan（第 2 轮测试时被关掉了），让 image-pan 重新注入
$settings = Join-Path $env:APPDATA 'dsh-manager\settings.json'
$obj = Get-Content $settings -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
if (-not $obj) { $obj = [pscustomobject]@{ LogLines = 800; WebPan = $true; WebDragOut = $true } }
$obj.WebPan = $true
$obj.WebDragOut = $true
Set-Content $settings (ConvertTo-Json $obj -Depth 5) -Encoding UTF8
Write-Output ('settings=' + ((Get-Content $settings -Raw) -replace "`r`n", ' '))

# 2) 换掉旧的 fakepage 服务（旧 server 还占着 3081）
$procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -like '*fakepage.js*' }
foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force } catch {} }
Start-Sleep -Seconds 2
Remove-Item 'C:\Users\User\fakepage.log' -Force -ErrorAction SilentlyContinue
Remove-Item 'C:\Users\User\fakepage.cmd.txt' -Force -ErrorAction SilentlyContinue

# 3) 直接在服务会话里起服务（不需要交互桌面）
$p2 = Start-Process -FilePath $node -ArgumentList 'C:\Users\User\fakepage.js' -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3
Write-Output ('server_pid=' + $(if ($p2) { $p2.Id } else { 'none' }))
Write-Output ('port=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
try { $r = Invoke-WebRequest 'http://127.0.0.1:3081/' -UseBasicParsing -TimeoutSec 6; Write-Output ('page=' + $r.StatusCode + ' hascmd=' + ($r.Content -like '*fetch(''/cmd''*')) } catch { Write-Output ('page FAILED: ' + $_.Exception.Message) }
