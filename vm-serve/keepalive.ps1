$exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Start-Process $exe
Start-Sleep -Seconds 10
$p = @(Get-Process DshManager -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 1 })
"count=" + $p.Count | Set-Content C:\Users\User\keepalive.txt -Encoding UTF8
foreach ($x in $p) { "pid=$($x.Id)" | Add-Content C:\Users\User\keepalive.txt -Encoding UTF8 }
# 保持任务存活，避免任务结束时把管理器一起带走
Start-Sleep -Seconds 7200
