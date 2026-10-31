# Pull VM-only state back to the host so a checkpoint rollback cannot eat it again.
#
# Run from the repo root on the host (Windows PowerShell 5.1 compatible):
#   powershell -ExecutionPolicy Bypass -File tools\host\pull-vm-backup.ps1
#   powershell -ExecutionPolicy Bypass -File tools\host\pull-vm-backup.ps1 -Out C:\backup\vm
#   powershell -ExecutionPolicy Bypass -File tools\host\pull-vm-backup.ps1 -IncludeSessions
#
# Captures: ~/share (deliverables/debs/scripts), each instance's share/ and
#   dsh-home/profiles/ (incl. cordis.patch.yml), the manager registry + settings,
#   ~/.npmrc, the installed dsh-manager version from dpkg, and a listing of share/.
# Skips: model session bodies (dsh-home/sessions) unless -IncludeSessions is given.

[CmdletBinding()]
param(
    [string]$VmHost = '172.22.148.197',
    [string]$User = 'twinblade',
    [int]$Port = 22,
    [string]$Out = '',
    [switch]$IncludeSessions,
    [string]$SshKey = ''
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
if (-not $Out) { $Out = Join-Path $repo 'vm-backup' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$dest = Join-Path $Out "vm-$stamp"
New-Item -ItemType Directory -Path $dest -Force | Out-Null

$sshBase = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-p', "$Port")
if ($SshKey) { $sshBase += @('-i', $SshKey) }
$target = "$User@$VmHost"
$remoteTar = "/tmp/vm-backup-$stamp.tgz"
$sessions = if ($IncludeSessions) { '1' } else { '0' }

# Remote side packs from a file list (-T) so a non-matching glob cannot break tar.
$remote = @(
    'set -u',
    ('STAMP=' + $stamp),
    ('SESS=' + $sessions),
    ('OUT=' + $remoteTar),
    'cd "$HOME" || { echo "cd $HOME failed" >&2; exit 1; }',
    'LIST=/tmp/vm-backup-list-$STAMP.txt',
    ': > "$LIST"',
    'for p in share Program/*/share Program/*/dsh-home/profiles Program/*/logs .local/opt/*/share .local/opt/*/dsh-home/profiles .local/opt/*/logs .config/dsh-manager .npmrc; do',
    '  [ -e "$p" ] && printf ''%s\n'' "$p" >> "$LIST"',
    'done',
    'if [ "$SESS" = "1" ]; then',
    '  for p in Program/*/dsh-home .local/opt/*/dsh-home; do [ -e "$p" ] && printf ''%s\n'' "$p" >> "$LIST"; done',
    'fi',
    'echo "--- included paths ---"',
    'cat "$LIST"',
    'dpkg-query -W -f=''dsh-manager=${Version}\n'' dsh-manager > /tmp/vm-backup-dpkg-$STAMP.txt 2>/dev/null || true',
    'ls -lR "$HOME/share" > /tmp/vm-backup-sharelist-$STAMP.txt 2>/dev/null || true',
    'tar -czf "$OUT" --warning=no-file-changed -T "$LIST" -C /tmp "vm-backup-dpkg-$STAMP.txt" "vm-backup-sharelist-$STAMP.txt" 2>/dev/null',
    'echo "--- result ---"',
    'ls -l "$OUT" || exit 1',
    'sha256sum "$OUT" || true'
) -join "`n"

$remoteScript = Join-Path $env:TEMP "vm-backup-remote-$stamp.sh"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($remoteScript, ($remote -replace "`r`n", "`n"), $utf8NoBom)

Write-Host "== upload remote script to $target =="
scp -o BatchMode=yes -P $Port $remoteScript "$($target):/tmp/vm-backup-run-$stamp.sh"

Write-Host "== pack on VM =="
ssh @sshBase $target "bash /tmp/vm-backup-run-$stamp.sh"

Write-Host "== fetch =="
scp -o BatchMode=yes -P $Port "$($target):$remoteTar" (Join-Path $dest 'vm-backup.tgz')

Write-Host "== clean remote temp files =="
ssh @sshBase $target "rm -f $remoteTar /tmp/vm-backup-run-$stamp.sh /tmp/vm-backup-list-$stamp.txt /tmp/vm-backup-dpkg-$stamp.txt /tmp/vm-backup-sharelist-$stamp.txt" | Out-Null

$tgz = Join-Path $dest 'vm-backup.tgz'
if (-not (Test-Path $tgz)) { throw "backup archive missing; check SSH and remote paths" }

$size = (Get-Item $tgz).Length
$sha = (Get-FileHash $tgz -Algorithm SHA256).Hash
$sessNote = if ($IncludeSessions) { 'included' } else { 'excluded (add -IncludeSessions)' }
$note = @(
    "VM backup $stamp",
    "source : $target",
    "file   : $tgz",
    ("size   : {0} bytes ({1:N1} MB)" -f $size, ($size / 1MB)),
    "sha256 : $sha",
    "content: ~/share, per-instance share/ and dsh-home/profiles/ (with cordis.patch.yml),",
    "         manager config, ~/.npmrc, dsh-manager dpkg version, share/ listing.",
    "sessions: $sessNote"
) -join "`n"
[System.IO.File]::WriteAllText((Join-Path $dest 'README.txt'), $note, $utf8NoBom)
Remove-Item $remoteScript -ErrorAction SilentlyContinue

Write-Host ("done: {0} ({1:N1} MB)" -f $tgz, ($size / 1MB))
Write-Host "sha256: $sha"
