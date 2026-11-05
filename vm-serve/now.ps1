$out='C:\Users\User\now.txt'
Remove-Item $out -ErrorAction SilentlyContinue
Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { "pid=$($_.Id) sess=$($_.SessionId) title=[$($_.MainWindowTitle)]" } | Add-Content $out
$ui = Join-Path $env:LOCALAPPDATA 'dsh-manager\ui.log'
if (Test-Path $ui) { "--- ui.log ---" | Add-Content $out; Get-Content $ui -Tail 8 | Add-Content $out }
