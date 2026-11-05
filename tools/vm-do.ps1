param(
    [Parameter(Mandatory=$true)][string]$Actions,
    [int]$Wait = 8,
    [string[]]$Shots = @()
)

$ErrorActionPreference = 'Continue'
$vmHost  = 'User@172.30.26.56'
$key     = '.tmp\vmtest_key'
$scpOpts = @('-i', $key, '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=NUL')
$sshOpts = $scpOpts + @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15')

$tmp = Join-Path $env:TEMP 'req.txt'
$lines = Get-Content $Actions | Where-Object { $_.Trim().Length -gt 0 }
[System.IO.File]::WriteAllLines($tmp, $lines, (New-Object System.Text.UTF8Encoding($false)))
& scp @scpOpts $tmp ($vmHost + ':C:/Users/User/req.txt') 2>&1 | Out-Null
Start-Sleep -Seconds $Wait

Write-Host '=== res ==='
$res = & ssh @sshOpts $vmHost 'powershell -NoProfile -Command "Get-Content C:\Users\User\res.txt -ErrorAction SilentlyContinue"' 2>&1
$res | Select-Object -First 40

foreach ($s in $Shots) {
    $dst = Join-Path 'vm-report' ($s + '.png')
    & scp @scpOpts ($vmHost + ':C:/Users/User/' + $s + '.png') $dst 2>&1 | Out-Null
    if (Test-Path $dst) { Write-Host ('png -> ' + $dst) }
}
