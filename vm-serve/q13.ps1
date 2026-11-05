Write-Output ('instances_dir=' + (Test-Path 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new'))
Write-Output ('kids=' + (@(Get-ChildItem 'C:\Users\User\AppData\Local\dsh-manager\instances' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
