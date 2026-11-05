$exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Start-Process explorer.exe -ArgumentList ('"' + $exe + '"')
Start-Sleep -Seconds 14
$p = @(Get-Process DshManager -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 1 })
"count=" + $p.Count | Set-Content C:\Users\User\startapp3.txt -Encoding UTF8
foreach ($x in $p) { "pid=$($x.Id) title=[$($x.MainWindowTitle)]" | Add-Content C:\Users\User\startapp3.txt -Encoding UTF8 }
