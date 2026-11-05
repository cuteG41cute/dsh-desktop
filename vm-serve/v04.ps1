$dir = 'C:\Users\User\AppData\Local\dsh-manager\instances\svctest'
Write-Output ('dir=' + (Test-Path $dir))
if (Test-Path $dir) { Write-Output ('kids=' + (@(Get-ChildItem $dir -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ',')) }
Write-Output ('node=' + (@(Get-Process node -ErrorAction SilentlyContinue).Count))
Write-Output ('port3081=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
Write-Output ('registry=' + ((Get-Content (Join-Path $env:APPDATA 'dsh-manager\instances.json') -Raw -ErrorAction SilentlyContinue) -replace "`r`n",' '))
