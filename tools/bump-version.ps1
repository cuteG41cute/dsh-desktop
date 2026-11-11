param(
    [Parameter(Mandatory = $true)][string]$Version
)

# 把 Windows / Linux 两端的版本号一次性改到同一个值（只改版本字段，不动依赖版本）。
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$parts = $Version.Split('.')
if ($parts.Count -lt 2) { throw "版本号格式应为 x.y.z，收到：$Version" }
$fileVersion = ($parts + @('0', '0', '0'))[0..3] -join '.'

$csproj = 'dsh-manager-win/DshManager.csproj'
$x = [System.IO.File]::ReadAllText((Resolve-Path $csproj), [System.Text.Encoding]::UTF8)
$x = [regex]::Replace($x, '<Version>[^<]+</Version>', "<Version>$Version</Version>")
$x = [regex]::Replace($x, '<FileVersion>[^<]+</FileVersion>', "<FileVersion>$fileVersion</FileVersion>")
$x = [regex]::Replace($x, '<AssemblyVersion>[^<]+</AssemblyVersion>', "<AssemblyVersion>$fileVersion</AssemblyVersion>")
[System.IO.File]::WriteAllText((Resolve-Path $csproj), $x, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "windows: $csproj -> $Version ($fileVersion)"

$core = 'dsh-desktop/linux/manager/dsh_manager/core.py'
$c = [System.IO.File]::ReadAllText((Resolve-Path $core), [System.Text.Encoding]::UTF8)
$c = [regex]::Replace($c, "MANAGER_VERSION = '[^']+'", "MANAGER_VERSION = '$Version'")
[System.IO.File]::WriteAllText((Resolve-Path $core), $c, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "linux:   $core -> $Version"

$deb = 'dsh-desktop/linux/manager/build-deb.sh'
$b = [System.IO.File]::ReadAllText((Resolve-Path $deb), [System.Text.Encoding]::UTF8)
$b = [regex]::Replace($b, '(?m)^VERSION="[^"]+"', "VERSION=`"$Version`"")
[System.IO.File]::WriteAllText((Resolve-Path $deb), $b, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "linux:   $deb -> $Version"

Write-Host ''
Write-Host '下一步：'
Write-Host '  1) powershell -File dsh-manager-win\build-win.ps1'
Write-Host '  2) wsl -d deepin -- bash "/mnt/c/Users/twinblade/Documents/deeepseek harness/dsh-desktop/linux/manager/build-deb.sh" --version ' + $Version
Write-Host '  3) 用 v' + $Version + ' 发同一个 Release（exe + deb 一起）'
