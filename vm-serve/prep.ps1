Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 3
Remove-Item 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new' -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new' | Out-Null
$tmp = Join-Path $env:TEMP 'm25.exe'
Invoke-WebRequest 'http://172.30.16.1:8899/DshManager.exe' -OutFile $tmp -UseBasicParsing
$dst = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Copy-Item $tmp $dst -Force
Write-Output ('version=' + (Get-Item $dst).VersionInfo.FileVersion)
Write-Output ('inst_clean=' + (@(Get-ChildItem 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new' -Force).Count -eq 0))
