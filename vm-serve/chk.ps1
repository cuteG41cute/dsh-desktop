Write-Output ('settings=' + (Get-Content (Join-Path $env:APPDATA 'dsh-manager\settings.json') -Raw -ErrorAction SilentlyContinue))
Get-Content (Join-Path $env:LOCALAPPDATA 'dsh-manager\web.log') -Tail 8 | ForEach-Object { Write-Output ('  ' + $_) }
