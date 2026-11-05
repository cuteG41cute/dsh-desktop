$dir = 'C:\Users\User\AppData\Local\dsh-manager\instances\svctest'
$node = Join-Path $dir 'node\node.exe'
Write-Output ('node_exists=' + (Test-Path $node))
$js = 'C:\Users\User\fake-service.js'
Write-Output ('js_exists=' + (Test-Path $js))
$out = & $node --version 2>&1
Write-Output ('ver=' + $out)
$p = Start-Process -FilePath $node -ArgumentList @($js, (Join-Path $dir 'held-open.dat')) -PassThru -WindowStyle Hidden -ErrorAction Continue
Start-Sleep -Seconds 3
Write-Output ('pid=' + $(if($p){$p.Id}else{'none'}) + ' exited=' + $(if($p){$p.HasExited}else{'?'}))
Write-Output ('port=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
