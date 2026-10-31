# Run a local script on the VM over SSH, then optionally fetch files back.
#
# Windows PowerShell 5.1 sends native arguments through a lossy quoter, so never
# pass shell snippets through ssh's command string: write a .sh/.py file and let
# this wrapper upload + execute it.
#
#   powershell -ExecutionPolicy Bypass -File tools\host\vm.ps1 -Script tools\host\probe-vm.sh
#   powershell -ExecutionPolicy Bypass -File tools\host\vm.ps1 -Script .\x.py -Args /tmp/a.png
#   powershell -ExecutionPolicy Bypass -File tools\host\vm.ps1 -Script .\x.sh -Fetch /tmp/out.png -FetchDir vm-shots

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Script,
    [string[]]$Args = @(),
    [string]$VmHost = '172.22.148.197',
    [string]$User = 'twinblade',
    [int]$Port = 22,
    [int]$TimeoutSec = 300,
    [string[]]$Fetch = @(),
    [string]$FetchDir = '',
    [switch]$Fixture,
    [string]$SshKey = ''
)

$ErrorActionPreference = 'Stop'
$sshBase = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-p', "$Port")
if ($SshKey) { $sshBase += @('-i', $SshKey) }
$target = "$User@$VmHost"

$src = (Resolve-Path $Script).Path
$ext = [System.IO.Path]::GetExtension($src)
$runsAs = switch ($ext) {
    '.py' { 'python3' }
    '.ps1' { throw 'upload a .sh or .py, not a .ps1' }
    default { 'bash' }
}
$stamp = [guid]::NewGuid().ToString('N').Substring(0, 8)
$remote = "/tmp/vmrun-$stamp$ext"

if ($Fixture) {
    $fix = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'vm_fixture.py'
    if (Test-Path $fix) {
        ssh @sshBase $target 'mkdir -p /tmp/dsh-vm' | Out-Null
        scp -o BatchMode=yes -P $Port $fix "$($target):/tmp/dsh-vm/vm_fixture.py" 2>$null
    }
}

scp -o BatchMode=yes -P $Port $src "$($target):$remote" 2>$null
if ($LASTEXITCODE -ne 0) { throw "upload failed for $src" }

$argLine = if ($Args.Count -gt 0) {
    ' ' + (($Args | ForEach-Object { "'" + ($_ -replace "'", "'\''") + "'" }) -join ' ')
} else { '' }
$cmdLine = "$runsAs $remote$argLine 2>&1; rc=`$?; rm -f $remote; exit `$rc"
Write-Host "== $runsAs $remote$argLine on $target =="
ssh @sshBase $target $cmdLine
$code = $LASTEXITCODE
Write-Host "== exit $code =="

if ($Fetch.Count -gt 0) {
    if (-not $FetchDir) { $FetchDir = 'vm-shots' }
    $repo = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
    $local = if ([System.IO.Path]::IsPathRooted($FetchDir)) { $FetchDir } else { Join-Path $repo $FetchDir }
    New-Item -ItemType Directory -Path $local -Force | Out-Null
    foreach ($f in $Fetch) {
        $name = Split-Path -Leaf $f
        scp -o BatchMode=yes -P $Port "$($target):$f" (Join-Path $local $name) 2>$null
        if ($LASTEXITCODE -eq 0) {
            $fi = Get-Item (Join-Path $local $name)
            Write-Host ("fetched {0} -> {1} ({2} bytes)" -f $f, $fi.FullName, $fi.Length)
        } else {
            Write-Host "fetch FAILED: $f"
        }
    }
}

exit $code
