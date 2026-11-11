param(
    [string]$Version = '1.5.8',
    [string]$VmHost = '172.30.22.155'
)
# Build the Linux deb, verify its contents, install on the VM, restart the session
# window and run JS assertions through the control socket. ASCII only.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$wslDir = ($here -replace '\\', '/') -replace '^C:', '/mnt/c'
$deb = Join-Path $here "dist\linux\dsh-manager_$($Version)_all.deb"

Write-Host '=== 1) build ==='
$buildCmd = "cd '$wslDir/dsh-desktop/linux/manager' && bash build-deb.sh --version $Version --out '$wslDir/dist/linux' > /tmp/build.log 2>&1; echo RC=$?"
wsl -d deepin -- bash -lc $buildCmd
if (-not (Test-Path $deb)) { throw "deb not found: $deb" }
Write-Host ("deb: {0} ({1:N0} bytes)" -f $deb, (Get-Item $deb).Length)

Write-Host '=== 2) verify deb contains js action ==='
$probe = "dpkg-deb --fsys-tarfile '$wslDir/dist/linux/dsh-manager_$($Version)_all.deb' | tar -xO ./usr/lib/dsh-manager/share/dsh-desktop.py | grep -c `"startswith('js `""
$count = (wsl -d deepin -- bash -lc $probe) -join ''
Write-Host ("js-action count in deb: {0}" -f $count.Trim())
if ($count.Trim() -ne '1') { throw 'deb does not contain the js control action - build did not pick up the patch' }

Write-Host '=== 3) install on VM ==='
scp -o BatchMode=yes -P 22 $deb "twinblade@${VmHost}:/tmp/dsh-manager.deb" | Out-Null
$remote = @'
set -u
sudo -n dpkg -i /tmp/dsh-manager.deb >/dev/null 2>&1 || true
echo -n "installed: "; dpkg-query -W -f='${Version}\n' dsh-manager
echo -n "system js action: "; grep -c "startswith('js " /usr/lib/dsh-manager/share/dsh-desktop.py || true
'@
Get-Content -Raw -Path (Join-Path $here '.tmp\remote-install.sh') -ErrorAction SilentlyContinue | Out-Null
$remote | ssh -p 22 -o BatchMode=yes "twinblade@$VmHost" "cat > /tmp/ri.sh; bash /tmp/ri.sh" 2>&1 | ForEach-Object { Write-Host $_ }

