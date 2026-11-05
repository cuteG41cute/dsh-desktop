$p = Join-Path $env:LOCALAPPDATA 'dsh-manager\web.log'
Write-Output ('weblog=' + (Test-Path $p))
if (Test-Path $p) { Get-Content $p -Tail 12 | ForEach-Object { Write-Output ('  ' + $_) } }
