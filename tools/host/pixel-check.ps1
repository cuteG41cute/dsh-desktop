# Run the three UI gates in one shot (pre-release / after any UI change).
#
#   powershell -ExecutionPolicy Bypass -File tools\host\pixel-check.ps1
#   powershell -ExecutionPolicy Bypass -File tools\host\pixel-check.ps1 -Update
#
# 1. token-diff.py     palette: design CSS variables vs themes.json (no pixels involved)
# 2. geometry-gate.py  geometry: design spec vs GTK allocations (engine independent, +/-2px)
# 3. pixel-gate.py     pixels: per-theme MAE (regression ratchet; font AA sets a floor)
#
# Prerequisite: vm-shots\gtk\ holds the 28 renders produced by tools\host\vm-gtk-shot.py.
# NOTE: keep this file ASCII-only - Windows PowerShell 5.1 reads .ps1 as ANSI,
#       so non-ASCII text without a BOM breaks the parser.
[CmdletBinding()]
param(
    [switch]$Update,
    [string]$Repo = ''
)

$ErrorActionPreference = 'Continue'
if (-not $Repo) {
    $Repo = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
}
Push-Location $Repo
$fail = 0

Write-Host '==== 1/3 palette gate (token-diff) ===='
python tools\host\token-diff.py --strict
if ($LASTEXITCODE -ne 0) { $fail = 1 }

Write-Host ''
Write-Host '==== 2/3 geometry gate (geometry-gate) ===='
$geoArgs = @('tools\host\geometry-gate.py')
if ($Update) { $geoArgs += '--update' }
python $geoArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host '  (geometry over tolerance - see the "over" rows above)'
    $fail = 1
}

Write-Host ''
Write-Host '==== 3/3 pixel gate (pixel-gate) ===='
$pixArgs = @('tools\host\pixel-gate.py')
if ($Update) { $pixArgs += '--update' }
python $pixArgs
if ($LASTEXITCODE -ne 0) { $fail = 1 }

Write-Host ''
if ($fail -ne 0) {
    Write-Host 'RESULT: FAIL (a gate did not pass)'
} else {
    Write-Host 'RESULT: PASS (palette / geometry / pixels all green)'
}
Pop-Location
exit $fail
