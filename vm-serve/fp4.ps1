$procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -like '*fakepage.js*' }
Write-Output ('node_fakepage=' + (@($procs).Count))
foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force } catch {} }
Start-Sleep -Seconds 2
schtasks /run /tn fakepage 2>&1 | Out-Null
Start-Sleep -Seconds 5
try { $r = Invoke-WebRequest 'http://127.0.0.1:3081/' -UseBasicParsing -TimeoutSec 8; Write-Output ('len=' + $r.RawContentLength + ' hasImg=' + ($r.Content -like '*#im{*')) } catch { Write-Output ('FAILED ' + $_.Exception.Message) }
