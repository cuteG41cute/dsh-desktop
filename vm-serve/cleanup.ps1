$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
# 清掉本轮测试临时造的东西，别把 VM 弄脏
Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 2
$procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -like '*fakepage*' -or $_.CommandLine -like '*fake-service*' }
foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force } catch {} }
foreach ($d in @('svctest')) {
    $p = Join-Path $root $d
    if (Test-Path $p) { Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue }
}
$reg = Join-Path $env:APPDATA 'dsh-manager\instances.json'
Set-Content $reg '[]' -Encoding UTF8
Write-Output ('instances=' + (@(Get-ChildItem $root -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
Write-Output ('registry=' + ((Get-Content $reg -Raw) -replace "`r`n", ' '))
Write-Output ('node=' + (@(Get-Process node -ErrorAction SilentlyContinue).Count))
Write-Output ('mgr=' + (@(Get-Process DshManager -ErrorAction SilentlyContinue).Count))
