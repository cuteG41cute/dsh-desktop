$log = 'C:\Users\User\diagapp.txt'
Remove-Item $log -ErrorAction SilentlyContinue
$ui = Join-Path $env:LOCALAPPDATA 'dsh-manager\ui.log'
"ui.log exists: " + (Test-Path $ui) | Add-Content $log
if (Test-Path $ui) { Get-Content $ui -Tail 20 | ForEach-Object { "  " + $_ } | Add-Content $log }
$exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
$p = Start-Process $exe -PassThru
Start-Sleep -Seconds 8
"process: " + $(if($p -and -not $p.HasExited){"alive pid=" + $p.Id}else{"EXITED code=" + $(if($p){$p.ExitCode}else{'?'})}) | Add-Content $log
"any dshmgr: " + (@(Get-Process DshManager -ErrorAction SilentlyContinue).Count) | Add-Content $log
