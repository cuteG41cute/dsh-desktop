$exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Start-Process $exe
Start-Sleep -Seconds 12
"started=" + (@(Get-Process DshManager -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 1 }).Count) | Set-Content C:\Users\User\startapp.txt -Encoding UTF8
"ver=" + (Get-Item $exe).VersionInfo.FileVersion | Add-Content C:\Users\User\startapp.txt -Encoding UTF8
