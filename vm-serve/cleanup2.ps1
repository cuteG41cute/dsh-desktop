$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
$p = Join-Path $root 'dsh-a'
if (Test-Path $p) {
    Write-Output ('size_MB=' + [math]::Round((Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB, 1))
    Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Output ('instances=' + (@(Get-ChildItem $root -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))

# 把 VM 里的管理器更新到最新（2.0.27），方便下次手动验证
$tmp = Join-Path $env:TEMP 'mgr-latest.exe'
try {
    Invoke-WebRequest 'http://172.30.16.1:8899/DshManager.exe' -OutFile $tmp -UseBasicParsing -TimeoutSec 60
    $dst = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
    Copy-Item $tmp $dst -Force
    Write-Output ('version=' + (Get-Item $dst).VersionInfo.FileVersion)
} catch {
    Write-Output ('update failed: ' + $_.Exception.Message)
}
