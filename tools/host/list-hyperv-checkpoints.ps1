# List Hyper-V checkpoints, and optionally export one to a folder (needs elevation).
#
# Why: dsh-manager 1.4.0 was built inside the VM and lost when the VM was rolled back.
# A checkpoint taken before/after that work still holds the old disk. Export it (do NOT
# apply it) and the 1.4.0 deb + source can be pulled out of the exported disk.
#
# Run in an ELEVATED PowerShell (right-click > Run as administrator):
#   powershell -ExecutionPolicy Bypass -File tools\host\list-hyperv-checkpoints.ps1
#   powershell -ExecutionPolicy Bypass -File tools\host\list-hyperv-checkpoints.ps1 -ExportSnapshot 'ubuntu-26.04' '2026-10-30 22-xx' -Dest 'D:\vmsnap'
#
# Export-VMSnapshot writes a full VM copy (disk + config). It does NOT touch the running VM.

[CmdletBinding()]
param(
    [string]$VMName = '',
    [string]$ExportSnapshot = '',
    [string]$SnapshotName = '',
    [string]$Dest = ''
)

$ErrorActionPreference = 'Stop'

function Test-Elevated {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object System.Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Elevated)) {
    Write-Host "NOT elevated. Open PowerShell as administrator and re-run this script." -ForegroundColor Yellow
    Write-Host "Without elevation Hyper-V cannot even list VMs ('required permission')."
    exit 1
}

Get-VM | Select-Object Name, State, Generation, Path | Format-Table -AutoSize

if ($VMName) { $vms = Get-VM -Name $VMName } else { $vms = Get-VM }

Write-Host "`n== Checkpoints (newest first) =="
$snaps = foreach ($vm in $vms) {
    Get-VMSnapshot -VMName $vm.Name -ErrorAction SilentlyContinue |
        Select-Object VMName, Name, CreationTime, SnapshotType, ParentSnapshotName
}
if (-not $snaps) {
    Write-Host "no checkpoints found" -ForegroundColor Yellow
} else {
    $snaps | Sort-Object CreationTime -Descending | Format-Table -AutoSize
}

if ($ExportSnapshot) {
    if (-not $Dest) { throw "-Dest is required with -ExportSnapshot" }
    $vm = if ($VMName) { $VMName } else { throw "-VMName is required with -ExportSnapshot" }
    $snap = if ($SnapshotName) { $SnapshotName } else { $ExportSnapshot }
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    Write-Host "`n== exporting snapshot '$snap' of '$vm' to $Dest (the live VM is not modified) =="
    Export-VMSnapshot -VMName $vm -Name $snap -Path $Dest
    Get-ChildItem -Path $Dest -Recurse -Filter *.vhdx |
        Select-Object FullName, @{ n = 'SizeGB'; e = { [math]::Round($_.Length / 1GB, 2) } }, LastWriteTime |
        Format-Table -AutoSize
    Write-Host "`nNext: import it as a COPY (Hyper-V Manager > Import Virtual Machine > 'Copy the virtual machine'),"
    Write-Host "boot it, then copy ~/share/*.deb and the 1.4.0 source tree out (scp or the SMB share)."
}
