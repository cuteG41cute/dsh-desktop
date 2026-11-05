param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][string]$Actions,
    [int]$Wait = 15,
    [string[]]$Shots = @()
)

$ErrorActionPreference = 'Continue'
$vmHost  = 'User@172.30.26.56'
$key     = '.tmp\vmtest_key'
$scpOpts = @('-i', $key, '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=NUL')
$sshOpts = $scpOpts + @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15')

$base = Get-Content 'vm-serve\act.ps1' -Raw
$lines = Get-Content $Actions | Where-Object { $_.Trim().Length -gt 0 } | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }
$literal = '@(' + ($lines -join ',') + ')'
$marker = '$actions = Get-Content ''C:\Users\User\actions.txt'' -ErrorAction SilentlyContinue'
$run = $base.Replace($marker, ('$actions = ' + $literal))
if (-not $run.Contains($literal)) { Write-Host 'WARN: action injection failed'; exit 1 }
$runFile = Join-Path $env:TEMP ('actrun_' + $Name + '.ps1')
[System.IO.File]::WriteAllText($runFile, $run, (New-Object System.Text.UTF8Encoding($true)))

$vbsBody = 'CreateObject("WScript.Shell").Run "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\User\actrun_' + $Name + '.ps1", 0, False' + "`r`n"
$tmpVbs = Join-Path $env:TEMP ('actrun_' + $Name + '.vbs')
[System.IO.File]::WriteAllText($tmpVbs, $vbsBody, [System.Text.Encoding]::ASCII)

& scp @scpOpts $runFile ($vmHost + ':C:/Users/User/actrun_' + $Name + '.ps1') 2>&1 | Out-Null
& scp @scpOpts $tmpVbs  ($vmHost + ':C:/Users/User/actrun_' + $Name + '.vbs') 2>&1 | Out-Null

& ssh @sshOpts $vmHost ('schtasks /create /tn ' + $Name + ' /tr C:\Users\User\actrun_' + $Name + '.vbs /sc once /st 00:00 /ru User /it /f') 2>&1 | Out-Null
& ssh @sshOpts $vmHost ('schtasks /end /tn ' + $Name) 2>&1 | Out-Null
& ssh @sshOpts $vmHost ('schtasks /run /tn ' + $Name) 2>&1 | Out-Null
Start-Sleep -Seconds $Wait

Write-Host '=== act.out ==='
& ssh @sshOpts $vmHost 'cmd /c type C:\Users\User\act.out.txt' 2>&1 | Select-Object -First 80

foreach ($s in $Shots) {
    $dst = Join-Path 'vm-report' ($s + '.png')
    & scp @scpOpts ($vmHost + ':C:/Users/User/' + $s + '.png') $dst 2>&1 | Out-Null
    if (Test-Path $dst) { Write-Host ('png -> ' + $dst) }
}
