$tmp = Join-Path $env:TEMP 'm21.exe'
Invoke-WebRequest 'http://172.30.16.1:8899/DshManager.exe' -OutFile $tmp -UseBasicParsing
$dst = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 3
Copy-Item $tmp $dst -Force
Write-Output ('version=' + (Get-Item $dst).VersionInfo.FileVersion)
