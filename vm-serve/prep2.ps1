$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 3
Remove-Item (Join-Path $root 'dsh-a-2') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $env:TEMP 'dsh-node-*.zip') -Force -ErrorAction SilentlyContinue
$tmp = Join-Path $env:TEMP 'm26.exe'
Invoke-WebRequest 'http://172.30.16.1:8899/DshManager.exe' -OutFile $tmp -UseBasicParsing
$dst = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Copy-Item $tmp $dst -Force
Write-Output ('version=' + (Get-Item $dst).VersionInfo.FileVersion)
Write-Output ('dirs=' + (@(Get-ChildItem $root -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
Write-Output ('seed=' + (Test-Path (Join-Path $root 'dsh-a\node\node.exe')))
