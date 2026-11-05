$procs = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*agent.ps1*' }
foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force } catch {} }
Start-Sleep -Seconds 2
schtasks /run /tn dshagent 2>&1 | Out-Null
Start-Sleep -Seconds 5
$again = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*agent.ps1*' }
Write-Output ('agents=' + (@($again).Count))
