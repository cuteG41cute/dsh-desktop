# 在【管理员】PowerShell 里运行：装 OpenSSH Server + 装测试公钥 + 打印 IP
$ErrorActionPreference = 'Continue'
Write-Host "== 1/4 安装 OpenSSH Server ==" -ForegroundColor Cyan
$cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*' | Select-Object -First 1
if ($cap.State -ne 'Installed') { Add-WindowsCapability -Online -Name $cap.Name | Out-Null }
Write-Host ("   state = " + (Get-WindowsCapability -Online -Name 'OpenSSH.Server*' | Select-Object -First 1).State)

Write-Host "== 2/4 启动 sshd 并设为自动 ==" -ForegroundColor Cyan
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
Write-Host ("   sshd = " + (Get-Service sshd).Status)

Write-Host "== 3/4 放行 22 端口 + 装公钥 ==" -ForegroundColor Cyan
if (-not (Get-NetFirewallRule -Name 'sshd' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (dsh test)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}
$key = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM0atbn57ZmhXONLNniUKlB493VvcfhhDRQ68v9jVdq0 dsh-manager-vm-test'
$dir = Join-Path $env:ProgramData 'ssh'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$f = Join-Path $dir 'administrators_authorized_keys'
if (-not (Test-Path $f)) { New-Item -ItemType File -Path $f | Out-Null }
$cur = Get-Content $f -Raw -ErrorAction SilentlyContinue
if ($cur -notlike "*$key*") { Add-Content -Path $f -Value $key -Encoding ascii }
icacls $f /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" | Out-Null
Write-Host ("   authorized_keys 行数 = " + (Get-Content $f | Measure-Object).Count)

Write-Host "== 4/4 网络信息 ==" -ForegroundColor Cyan
Write-Host ("   用户名 : " + $env:USERNAME)
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object IPAddress, InterfaceAlias | Format-Table -AutoSize | Out-String | Write-Host
Write-Host "完成：把上面的 IPv4 和用户名发回去即可。" -ForegroundColor Green
