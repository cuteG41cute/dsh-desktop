param(
    [Parameter(Mandatory=$true)][string]$Script,
    [string]$RemoteName = ''
)

$ErrorActionPreference = 'Continue'
$vmHost  = 'User@172.30.26.56'
$key     = '.tmp\vmtest_key'
$scpOpts = @('-i', $key, '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=NUL')
$sshOpts = $scpOpts + @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15')

if (-not $RemoteName) { $RemoteName = [System.IO.Path]::GetFileNameWithoutExtension($Script) }
$remote = 'C:/Users/User/' + $RemoteName + '.ps1'
& scp @scpOpts $Script ($vmHost + ':' + $remote) 2>&1 | Out-Null
$cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\User\' + $RemoteName + '.ps1'
& ssh @sshOpts $vmHost $cmd 2>&1 | Select-Object -First 80
