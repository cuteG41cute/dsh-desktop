Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 3
$exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Start-Process -FilePath $exe -ArgumentList '--shot-window'
Start-Sleep -Seconds 22
Write-Output ('mgr=' + (@(Get-Process DshManager -ErrorAction SilentlyContinue).Count))
$p = Join-Path $env:LOCALAPPDATA 'dsh-manager\web.log'
if (Test-Path $p) { Get-Content $p -Tail 8 | ForEach-Object { Write-Output ('  ' + $_) } }
