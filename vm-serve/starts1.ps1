Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ('pid=' + $_.Id + ' sess=' + $_.SessionId + ' title=[' + $_.MainWindowTitle + ']') }
$p = Join-Path $env:LOCALAPPDATA 'dsh-manager\web.log'
Write-Output ('weblog_mtime=' + (Get-Item $p -ErrorAction SilentlyContinue).LastWriteTime.ToString('HH:mm:ss'))
Get-Content $p -Tail 4 -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ('  ' + $_) }
Write-Output ('port=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
