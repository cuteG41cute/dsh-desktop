# Install the Windows manager per-user (no admin needed).
#   powershell -ExecutionPolicy Bypass -File install-win.ps1
[CmdletBinding()]
param(
    [string]$Dir = '',
    [switch]$NoShortcut
)

$ErrorActionPreference = 'Stop'
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Dir) { $Dir = Join-Path $env:LOCALAPPDATA 'Programs\DSH Manager' }

Write-Host "== install to $Dir"
New-Item -ItemType Directory -Path $Dir -Force | Out-Null
Copy-Item (Join-Path $src 'DshManager.exe') $Dir -Force
foreach ($extra in @('README-win.md', 'uninstall-win.ps1')) {
    $p = Join-Path $src $extra
    if (Test-Path $p) { Copy-Item $p $Dir -Force }
}

if (-not $NoShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $name = 'DeepSeek Harness Manager.lnk'
    $targets = @(
        (Join-Path ([Environment]::GetFolderPath('Desktop')) $name),
        (Join-Path ([Environment]::GetFolderPath('Programs')) $name)
    )
    foreach ($lnkPath in $targets) {
        $sc = $shell.CreateShortcut($lnkPath)
        $sc.TargetPath = Join-Path $Dir 'DshManager.exe'
        $sc.WorkingDirectory = $Dir
        $sc.IconLocation = (Join-Path $Dir 'DshManager.exe') + ',0'
        $sc.Description = 'DeepSeek Harness Manager'
        $sc.Save()
        Write-Host "   shortcut: $lnkPath"
    }
}

Write-Host '== done. First start creates %APPDATA%\dsh-manager and %LOCALAPPDATA%\dsh-manager\webview2.'
