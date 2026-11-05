$p = 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-a'
Write-Output ('kids=' + (@(Get-ChildItem $p -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
Write-Output ('node_proc=' + (@(Get-Process node -ErrorAction SilentlyContinue).Count))
Write-Output ('dist_cli=' + (Test-Path (Join-Path $p 'app\apps\cli\dist')))
$home = Join-Path $p 'dsh-home'
Write-Output ('home=' + (Test-Path $home))
if (Test-Path $home) { Write-Output ('home_kids=' + (@(Get-ChildItem $home -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ',')) }
