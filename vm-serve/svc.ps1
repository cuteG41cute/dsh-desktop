$logs = 'C:\Users\User\AppData\Local\dsh-manager\logs'
Get-ChildItem $logs | ForEach-Object { Write-Output ('file=' + $_.Name + ' size=' + $_.Length) }
$log = Get-ChildItem $logs -Filter *.log | Select-Object -First 1
if ($log) { Write-Output '--- tail ---'; Get-Content $log.FullName -Tail 10 | ForEach-Object { Write-Output ('  ' + $_) } }
Write-Output ('port3081=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
Write-Output ('node_procs=' + (@(Get-Process node -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }) -join ','))
