#requires -Version 3.0
<#
把只监听 127.0.0.1 的代理，转发成虚拟机可用的地址（Windows 半边）。

  proxy-relay.ps1 -Start       background start (hidden)
  proxy-relay.ps1 -Stop        stop
  proxy-relay.ps1 -Status      running? + log tail
  proxy-relay.ps1 -Install     autostart at logon (Startup shortcut) + start now
  proxy-relay.ps1 -Uninstall   remove autostart + stop

VM side then uses http://<hyper-v-host-ip>:7891 as its proxy
(default 172.22.144.1:7891 -> 127.0.0.1:7890). Change the listen address with
  proxy-relay.ps1 -Start -Listen 0.0.0.0:7891

ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI.
#>
[CmdletBinding()]
param(
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status,
    [switch]$Install,
    [switch]$Uninstall,
    [string]$Listen = '',
    [string]$Target = ''
)

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$relay = Join-Path $here 'proxy-relay.py'
$state = Join-Path $env:LOCALAPPDATA 'dsh-proxy'
$pidFile = Join-Path $state 'relay.pid'
$logFile = Join-Path $state 'relay.log'
$listenFile = Join-Path $state 'listen.txt'
$lnkName = 'DSH-proxy-relay.lnk'
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
    $raw = Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $raw) { return $null }
    $procId = 0
    if (-not [int]::TryParse($raw, [ref]$procId)) { return $null }
    if (-not (Get-Process -Id $procId -ErrorAction SilentlyContinue)) { return $null }
    return $procId
}

function Get-Args {
    $a = @()
    if ($Listen) { $a += @('--listen', $Listen) }
    if ($Target) { $a += @('--target', $Target) }
    return ($a -join ' ')
}

function Start-Relay {
    $running = Get-RunningPid
    if ($running) { Write-Host "already running (pid $running)"; return }
    if (-not (Test-Path $relay)) { throw "missing $relay" }
    New-Item -ItemType Directory -Path $state -Force | Out-Null
    $pyw = Get-Pythonw
    $extra = Get-Args
    if ($Listen) { Set-Content -Path $listenFile -Value $Listen -Encoding ascii }
    $argLine = '"' + $relay + '"'
    if ($extra) { $argLine = $argLine + ' ' + $extra }
    $proc = Start-Process -FilePath $pyw -ArgumentList $argLine -WorkingDirectory $here `
        -WindowStyle Hidden -RedirectStandardError $logFile -PassThru
    Set-Content -Path $pidFile -Value $proc.Id -Encoding ascii
    Start-Sleep -Milliseconds 900
    if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
        Write-Host "started (pid $($proc.Id)) log=$logFile"
    } else {
        Write-Host "failed to start; see $logFile"
        exit 1
    }
}

function Stop-Relay {
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
    if ($running) { Write-Host "running (pid $running)" } else { Write-Host 'stopped' }
    if (Test-Path $lnk) { Write-Host "autostart: $lnk" } else { Write-Host 'autostart: off' }
    if (Test-Path $logFile) {
        Write-Host ''
        Write-Host "== last 8 log lines ($logFile)"
        Get-Content -Path $logFile -Tail 8 -Encoding UTF8 | ForEach-Object { Write-Host "  $_" }
    }
    try {
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalPort -in 7890, 7891 } |
            Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table -AutoSize
    } catch { }
}

function Install-Autostart {
    New-Item -ItemType Directory -Path $state -Force | Out-Null
    $pyw = Get-Pythonw
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = $pyw
    $argLine = '"' + $relay + '"'
    $extra = Get-Args
    if ($extra) { $argLine = $argLine + ' ' + $extra }
    $sc.Arguments = $argLine
    $sc.WorkingDirectory = $here
    $sc.WindowStyle = 7
    $sc.Description = 'DSH proxy relay (VM -> host proxy)'
    $sc.Save()
    Write-Host "autostart installed: $lnk"
    Start-Relay
}

function Remove-Autostart {
    if (Test-Path $lnk) {
        Remove-Item $lnk -Force
        Write-Host "autostart removed: $lnk"
    } else {
        Write-Host 'autostart was not installed'
    }
    Stop-Relay
}

if ($Install) { Install-Autostart; exit 0 }
if ($Uninstall) { Remove-Autostart; exit 0 }
if ($Start) { Start-Relay; exit 0 }
if ($Stop) { Stop-Relay; exit 0 }
if ($Status) { Show-Status; exit 0 }

Write-Host 'usage: proxy-relay.ps1 -Start|-Stop|-Status|-Install|-Uninstall [-Listen host:port] [-Target host:port]'
