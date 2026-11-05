$ErrorActionPreference = 'Continue'
$log = 'C:\Users\User\upgrade.txt'
"start" | Set-Content $log -Encoding UTF8
$tmp = Join-Path $env:TEMP 'dshmgr-new.exe'
Invoke-WebRequest 'http://172.30.16.1:8899/DshManager.exe' -OutFile $tmp -UseBasicParsing
"downloaded=" + (Test-Path $tmp) + " size=" + (Get-Item $tmp).Length | Add-Content $log
Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 3
$dst = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Copy-Item $tmp $dst -Force
"version=" + (Get-Item $dst).VersionInfo.FileVersion | Add-Content $log
