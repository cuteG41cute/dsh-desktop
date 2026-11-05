param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][string]$Script,
    [int]$Wait = 12,
    [switch]$FetchPng
)

$ErrorActionPreference = 'Continue'
$vmHost = 'User@172.30.26.56'
$key    = '.tmp\vmtest_key'
$scpOpts = @('-i', $key, '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=NUL')
$sshOpts = $scpOpts + @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15')

$remotePs1 = 'C:/Users/User/' + $Name + '.ps1'
$remoteCmd = 'C:/Users/User/' + $Name + '.cmd'

& scp @scpOpts $Script ($vmHost + ':' + $remotePs1) 2>&1 | Out-Null

$cmdBody = "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\User\$Name.ps1`r`n"
$tmpCmd = Join-Path $env:TEMP ($Name + '.cmd')
[System.IO.File]::WriteAllText($tmpCmd, $cmdBody, [System.Text.Encoding]::ASCII)
& scp @scpOpts $tmpCmd ($vmHost + ':' + $remoteCmd) 2>&1 | Out-Null

& ssh @sshOpts $vmHost ("schtasks /create /tn $Name /tr C:\Users\User\$Name.cmd /sc once /st 00:00 /ru User /it /f") 2>&1 | Out-Null
& ssh @sshOpts $vmHost ("schtasks /end /tn $Name") 2>&1 | Out-Null
& ssh @sshOpts $vmHost ("schtasks /run /tn $Name") 2>&1 | Out-Null
Start-Sleep -Seconds $Wait

Write-Host "=== $Name.out ==="
& ssh @sshOpts $vmHost ("cmd /c type C:\Users\User\$Name.out.txt") 2>&1 | Select-Object -First 60

if ($FetchPng) {
    $dst = Join-Path 'vm-report' ($Name + '.png')
    & scp @scpOpts ($vmHost + ':C:/Users/User/' + $Name + '.png') $dst 2>&1 | Out-Null
    if (Test-Path $dst) { Write-Host ("png -> " + $dst + " (" + (Get-Item $dst).Length + " bytes)") }
}
