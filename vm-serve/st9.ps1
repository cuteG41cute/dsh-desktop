Write-Output ('node=' + (@(Get-Process node -ErrorAction SilentlyContinue).Count))
Write-Output ('port3081=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
Write-Output ('dir=' + (Test-Path 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new'))
