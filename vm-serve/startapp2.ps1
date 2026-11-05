Remove-Item 'C:\Users\User\AppData\Local\dsh-manager\instances\vmtest' -Recurse -Force -ErrorAction SilentlyContinue
"removed_leftover=" + (-not (Test-Path 'C:\Users\User\AppData\Local\dsh-manager\instances\vmtest')) | Set-Content C:\Users\User\startapp.txt -Encoding UTF8
$exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Start-Process $exe
Start-Sleep -Seconds 12
"started=" + (@(Get-Process DshManager -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 1 }).Count) | Add-Content C:\Users\User\startapp.txt -Encoding UTF8
