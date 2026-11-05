Write-Output ('registry=' + ((Get-Content (Join-Path $env:APPDATA 'dsh-manager\instances.json') -Raw -ErrorAction SilentlyContinue) -replace "`r`n",' '))
$p = 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-a'
Write-Output ('dist=' + (Test-Path (Join-Path $p 'app\apps\cli\dist')))
Write-Output ('home=' + (Test-Path (Join-Path $p 'dsh-home')))
