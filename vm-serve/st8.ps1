Write-Output ('mgr=' + (@(Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { "$($_.Id)/$($_.SessionId)" }) -join ';'))
Write-Output ('dir=' + (Test-Path 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new'))
$ui = Join-Path $env:LOCALAPPDATA 'dsh-manager\ui.log'
if (Test-Path $ui) { Write-Output '--- ui.log tail ---'; Get-Content $ui -Tail 12 | ForEach-Object { Write-Output ('  ' + $_) } }
