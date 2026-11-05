$exe = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager\DshManager.exe'
Write-Output ("exe exists: " + (Test-Path $exe))
if (Test-Path $exe) { Write-Output ("version: " + (Get-Item $exe).VersionInfo.FileVersion) }
$p = Get-Process DshManager -ErrorAction SilentlyContinue
Write-Output ("proc count: " + (@($p).Count))
foreach ($x in @($p)) { Write-Output ("  pid=" + $x.Id + " title=" + $x.MainWindowTitle) }
$lg = Join-Path $env:LOCALAPPDATA 'dsh-manager\ui.log'
if (Test-Path $lg) { Write-Output "--- ui.log tail ---"; Get-Content $lg -Tail 10 | ForEach-Object { Write-Output ("  " + $_) } } else { Write-Output "no ui.log" }
Write-Output ("session id: " + [System.Diagnostics.Process]::GetCurrentProcess().SessionId)
Write-Output ("interactive: " + [Environment]::UserInteractive)
