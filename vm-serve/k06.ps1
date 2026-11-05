$dir = 'C:\Users\User\AppData\Local\dsh-manager\instances\faketest'
Write-Output ('dir=' + (Test-Path $dir))
Write-Output ('list=' + (@(Get-ChildItem 'C:\Users\User\AppData\Local\dsh-manager\instances' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
Write-Output ('registry=' + ((Get-Content (Join-Path $env:APPDATA 'dsh-manager\instances.json') -Raw -ErrorAction SilentlyContinue) -replace "`r`n",' '))
