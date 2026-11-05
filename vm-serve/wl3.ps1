$p = Join-Path $env:LOCALAPPDATA 'dsh-manager\web.log'
Get-Content $p -Tail 10 | ForEach-Object { Write-Output ('  ' + $_) }
Write-Output ('--- fakepage.log ---')
Get-Content 'C:\Users\User\fakepage.log' -Tail 6 -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ('  ' + $_) }
