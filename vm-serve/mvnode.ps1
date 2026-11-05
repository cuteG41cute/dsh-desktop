$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
$from = Join-Path $root 'dsh-new'
$to   = Join-Path $root 'dsh-a'
Remove-Item $to -Recurse -Force -ErrorAction SilentlyContinue
Move-Item $from $to -Force
Write-Output ('moved=' + (Test-Path (Join-Path $to 'node\node.exe')))
Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 2
$exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Start-Process $exe
Start-Sleep -Seconds 12
Write-Output ('mgr=' + (@(Get-Process DshManager -ErrorAction SilentlyContinue).Count))
