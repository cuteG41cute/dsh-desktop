# Build the Windows release (single self-contained exe) + installer folder.
#   powershell -ExecutionPolicy Bypass -File dsh-manager-win\build-win.ps1
# Output: dist\win  (DshManager.exe + install/uninstall scripts + README)
# ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI.
[CmdletBinding()]
param(
    [string]$Configuration = 'Release',
    [switch]$FrameworkDependent,
    [string]$AudioCppBin = ''
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

# Bundle the audio.cpp runtime with static eSpeak (English Kokoro voices need it).
# Source can be overridden with -AudioCppBin.
$runtimeSrc = if ($AudioCppBin) { $AudioCppBin } else { 'C:\Users\twinblade\Documents\audio.cpp\build-espeak-win\bin' }
$runtimeDst = Join-Path $here 'runtime'
if (Test-Path (Join-Path $runtimeSrc 'audiocpp_server.exe')) {
    New-Item -ItemType Directory -Path $runtimeDst -Force | Out-Null
    Copy-Item (Join-Path $runtimeSrc 'audiocpp_server.exe') (Join-Path $runtimeDst 'audiocpp_server.exe') -Force
    Copy-Item (Join-Path $runtimeSrc 'espeak-ng-data.bin') (Join-Path $runtimeDst 'espeak-ng-data.bin') -Force
    Write-Host "bundled runtime from $runtimeSrc"
} else {
    Write-Host "WARN: no audio.cpp runtime at $runtimeSrc; exe will download the official one instead"
}

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Path $out -Force | Out-Null

$a = @('publish', (Join-Path $here 'DshManager.csproj'),
    '-c', $Configuration, '-r', 'win-x64', '-o', $out, '--nologo',
    '-p:DebugType=None', '-p:DebugSymbols=false')
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

# 发布包里不需要调试符号和第三方 XML 文档
Get-ChildItem $out -Filter *.pdb -File -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem $out -Filter *.xml -File -ErrorAction SilentlyContinue | Remove-Item -Force

foreach ($f in @('install-win.ps1', 'uninstall-win.ps1', 'README-win.md')) {
    $p = Join-Path $here $f
    if (Test-Path $p) { Copy-Item $p $out -Force }
}
# 最新的发布说明也带上（按版本号取最新一份）
$notes = Get-ChildItem $here -Filter 'RELEASE-NOTES-win-*.md' -File -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
if ($notes) { Copy-Item $notes.FullName $out -Force }

$exe = Join-Path $out 'DshManager.exe'
if (-not (Test-Path $exe)) { throw 'DshManager.exe missing after publish' }
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
$all = [math]::Round(((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host ''
Write-Host "== done: $out"
Write-Host "   DshManager.exe = $size MB (folder total $all MB)"
