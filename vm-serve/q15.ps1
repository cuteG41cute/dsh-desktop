Write-Output ('dir_exists=' + (Test-Path 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new'))
Write-Output ('kids=' + (@(Get-ChildItem 'C:\Users\User\AppData\Local\dsh-manager\instances' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
Write-Output ('node_alive=' + (@(Get-Process node -ErrorAction SilentlyContinue).Count))
Write-Output ('port3081=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
