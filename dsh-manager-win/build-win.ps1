# Build the Windows release (single self-contained exe) + installer folder.
#   powershell -ExecutionPolicy Bypass -File dsh-manager-win\build-win.ps1
# Output: dist\win  (DshManager.exe + install/uninstall scripts + README)
# ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI.
[CmdletBinding()]
param(
    [string]$Configuration = 'Release',
    [switch]$FrameworkDependent
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$out = Join-Path $repo 'dist\win'

$dotnet = Join-Path $env:LOCALAPPDATA 'dotnet-sdk\dotnet.exe'
if (-not (Test-Path $dotnet)) {
    $c = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if ($c) { $dotnet = $c.Source } else { throw 'dotnet.exe not found' }
}

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Path $out -Force | Out-Null

$a = @('publish', (Join-Path $here 'DshManager.csproj'),
    '-c', $Configuration, '-r', 'win-x64', '-o', $out, '--nologo')
if ($FrameworkDependent) {
    $a += @('--self-contained', 'false')
} else {
    $a += @('--self-contained', 'true',
        '-p:PublishSingleFile=true',
        '-p:IncludeNativeLibrariesForSelfExtract=true',
        '-p:EnableCompressionInSingleFile=true')
}

Write-Host "== dotnet $($a -join ' ')"
& $dotnet @a
if ($LASTEXITCODE -ne 0) { throw "publish failed ($LASTEXITCODE)" }

foreach ($f in @('install-win.ps1', 'uninstall-win.ps1', 'README-win.md')) {
    $p = Join-Path $here $f
    if (Test-Path $p) { Copy-Item $p $out -Force }
}

$exe = Join-Path $out 'DshManager.exe'
if (-not (Test-Path $exe)) { throw 'DshManager.exe missing after publish' }
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
$all = [math]::Round(((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host ''
Write-Host "== done: $out"
Write-Host "   DshManager.exe = $size MB (folder total $all MB)"
