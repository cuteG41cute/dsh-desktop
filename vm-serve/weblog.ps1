$p = Join-Path $env:LOCALAPPDATA 'dsh-manager\web.log'
Write-Output ('weblog=' + (Test-Path $p))
if (Test-Path $p) { Get-Content $p -Tail 14 | ForEach-Object { Write-Output ('  ' + $_) } }
Write-Output ('win_count=' + (@(Get-Process DshManager -ErrorAction SilentlyContinue).Count))
