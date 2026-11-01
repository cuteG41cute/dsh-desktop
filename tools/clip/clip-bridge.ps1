#requires -Version 3.0
<#
DeepSeek Harness 本机 <-> 虚拟机 剪切板桥（Windows 半边）

  clip-bridge.ps1 -Start       start the bridge in the background (hidden)
  clip-bridge.ps1 -Stop        stop it
  clip-bridge.ps1 -Status      running? + last log lines
  clip-bridge.ps1 -Install     autostart at logon (Startup shortcut) + start now
  clip-bridge.ps1 -Uninstall   remove autostart + stop

The bridge itself is tools/clip/host-bridge.py (Windows clipboard <-> VM Wayland
clipboard over two ssh channels). Text only; images/files are left untouched.

ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI.
#>
[CmdletBinding()]
param(
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status,
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Deploy,
    [string]$VmHost = $(if ($env:DSH_CLIP_SSH) { $env:DSH_CLIP_SSH } else { 'twinblade@172.22.148.197' })
)

$ErrorActionPreference = 'Stop'

# The bridge log is UTF-8; show it correctly even on a GBK console.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bridge = Join-Path $here 'host-bridge.py'
$state = Join-Path $env:LOCALAPPDATA 'dsh-clip'
$pidFile = Join-Path $state 'bridge.pid'
$logFile = Join-Path $state 'bridge.log'
$lnkName = 'DSH-clipboard-bridge.lnk'
$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup $lnkName

function Get-Pythonw {
    $c = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $p = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($p) {
        $guess = Join-Path (Split-Path -Parent $p.Source) 'pythonw.exe'
        if (Test-Path $guess) { return $guess }
        return $p.Source
    }
    throw 'python.exe not found on PATH'
}

function Get-RunningPid {
    if (-not (Test-Path $pidFile)) { return $null }
    $raw = (Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $raw) { return $null }
    $procId = 0
    if (-not [int]::TryParse($raw, [ref]$procId)) { return $null }
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $p) { return $null }
    return $procId
}

function Start-Bridge {
    $running = Get-RunningPid
    if ($running) { Write-Host "already running (pid $running)"; return }
    if (-not (Test-Path $bridge)) { throw "missing $bridge" }
    New-Item -ItemType Directory -Path $state -Force | Out-Null
    $pyw = Get-Pythonw
    $proc = Start-Process -FilePath $pyw -ArgumentList ('"' + $bridge + '"') -WorkingDirectory $here `
        -WindowStyle Hidden -PassThru
    Set-Content -Path $pidFile -Value $proc.Id -Encoding ascii
    Start-Sleep -Milliseconds 800
    if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
        Write-Host "started (pid $($proc.Id)) -> $logFile"
    } else {
        Write-Host "failed to start; see $logFile"
        exit 1
    }
}

function Stop-Bridge {
    $running = Get-RunningPid
    if (-not $running) {
        Write-Host 'not running'
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        return
    }
    Stop-Process -Id $running -Force -ErrorAction SilentlyContinue
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Write-Host "stopped (pid $running)"
}

function Show-Status {
    $running = Get-RunningPid
    if ($running) {
        Write-Host "running (pid $running)"
    } else {
        Write-Host 'stopped'
    }
    if (Test-Path $lnk) { Write-Host "autostart: $lnk" } else { Write-Host 'autostart: off' }
    if (Test-Path $logFile) {
        Write-Host ''
        Write-Host "== last 12 log lines ($logFile)"
        Get-Content -Path $logFile -Tail 12 -Encoding UTF8 | ForEach-Object { Write-Host "  $_" }
    }
}

function Deploy-Vm {
    # Push the VM-side helpers (and make sure wl-clipboard exists), then restart.
    $files = @('vm-watch.py', 'vm-apply.py')
    foreach ($f in $files) {
        $src = Join-Path $here $f
        if (-not (Test-Path $src)) { throw "missing $src" }
    }
    & ssh -o BatchMode=yes $VmHost 'mkdir -p ~/.local/share/dsh-clip' | Out-Null
    foreach ($f in $files) {
        & scp -o BatchMode=yes (Join-Path $here $f) ($VmHost + ':~/.local/share/dsh-clip/') | Out-Null
    }
    & ssh -o BatchMode=yes $VmHost 'chmod +x ~/.local/share/dsh-clip/*.py; command -v wl-copy >/dev/null || sudo -n apt-get install -y -q wl-clipboard >/dev/null 2>&1; command -v wl-copy && echo "wl-clipboard ok" || echo "wl-clipboard MISSING"'
    Write-Host "deployed to $VmHost"
    Stop-Bridge | Out-Null
    Start-Bridge
}

function Install-Autostart {    New-Item -ItemType Directory -Path $state -Force | Out-Null
    $pyw = Get-Pythonw
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = $pyw
    $sc.Arguments = '"' + $bridge + '"'
    $sc.WorkingDirectory = $here
    $sc.WindowStyle = 7
    $sc.Description = 'DSH clipboard bridge (host <-> VM)'
    $sc.Save()
    Write-Host "autostart installed: $lnk"
    Start-Bridge
}

function Remove-Autostart {
    if (Test-Path $lnk) {
        Remove-Item $lnk -Force
        Write-Host "autostart removed: $lnk"
    } else {
        Write-Host 'autostart was not installed'
    }
    Stop-Bridge
}

if ($Install) { Install-Autostart; exit 0 }
if ($Deploy) { Deploy-Vm; exit 0 }
if ($Uninstall) { Remove-Autostart; exit 0 }
if ($Start) { Start-Bridge; exit 0 }
if ($Stop) { Stop-Bridge; exit 0 }
if ($Status) { Show-Status; exit 0 }

Write-Host 'usage: clip-bridge.ps1 -Start|-Stop|-Status|-Install|-Uninstall|-Deploy'
