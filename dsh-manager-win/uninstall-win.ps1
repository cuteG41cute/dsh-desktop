# Remove the Windows manager (per-user). Data folders kept unless -Purge.
#   powershell -ExecutionPolicy Bypass -File uninstall-win.ps1 [-Purge]
[CmdletBinding()]
param([switch]$Purge)

$ErrorActionPreference = 'Stop'
$Dir = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager'
Get-Process DshManager -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

$name = 'DeepSeek Harness Manager.lnk'
foreach ($lnk in @(
        (Join-Path ([Environment]::GetFolderPath('Desktop')) $name),
        (Join-Path ([Environment]::GetFolderPath('Programs')) $name))) {
    if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "  removed $lnk" }
}
if (Test-Path $Dir) { Remove-Item $Dir -Recurse -Force; Write-Host "  removed $Dir" }

if ($Purge) {
    foreach ($d in @((Join-Path $env:APPDATA 'dsh-manager'), (Join-Path $env:LOCALAPPDATA 'dsh-manager'))) {
        if (Test-Path $d) { Remove-Item $d -Recurse -Force; Write-Host "  purged $d" }
    }
}
Write-Host '== done (instance dirs and DSH data untouched)'
