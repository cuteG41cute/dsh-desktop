#Requires -Version 5.1
<#
.SYNOPSIS
  在 Windows 上建一个只给 Hyper-V 虚拟机用的 SMB 共享，并只对虚拟机网段放行 445。

.DESCRIPTION
  为什么要管理员：Windows 默认只有 C$ / ADMIN$ 两个管理共享，连接管理共享需要管理员组权限，
  而普通用户账号不在管理员组，所以必须新建一个普通共享 + 一条入站防火墙规则。

  脚本做的事（全部可撤销）：
    1. 建共享 <ShareName> -> <Path>，只给当前账号只读权限；
    2. 建入站防火墙规则，只放行 445/tcp，且来源限制在虚拟机网段（默认 172.22.144.0/20）；
    3. 打印 Ubuntu 里该执行的挂载命令。
  加 -Remove 则把上面两样删干净。

.EXAMPLE
  # 右键「使用 PowerShell 运行」，或在管理员 PowerShell 里：
  powershell -ExecutionPolicy Bypass -File .\windows-share.ps1

.EXAMPLE
  # 撤销（同样需要管理员）
  powershell -ExecutionPolicy Bypass -File .\windows-share.ps1 -Remove
#>
[CmdletBinding()]
param(
    # 要共享出去的目录（默认：管理器 .deb 所在目录）
    [string]$Path = "",

    # 共享名（Ubuntu 里 //主机/共享名 用这个）
    [string]$ShareName = "DSH-VM",

    # 允许连接该共享的 Windows 账号，默认当前账号
    [string]$Account = "",

    # 只对这些来源地址放行 445（Hyper-V Default Switch 是 172.22.144.0/20）
    [string]$RemoteAddress = "172.22.144.0/20",

    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$FirewallName = "DSH VM share (SMB 445)"

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host ""
    Write-Host "需要管理员权限。请用下面任一方式重开：" -ForegroundColor Yellow
    Write-Host "  1) 开始菜单搜 PowerShell -> 右键「以管理员身份运行」 -> 再执行本脚本"
    Write-Host "  2) 或右键本文件 ->「使用 PowerShell 运行」(会弹 UAC)"
    Write-Host ""
    exit 2
}

# ---------- 撤销 ----------
if ($Remove) {
    $done = @()
    $sh = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
    if ($sh) {
        Remove-SmbShare -Name $ShareName -Force
        $done += "已删除共享 \\$env:COMPUTERNAME\$ShareName"
    }
    $fw = Get-NetFirewallRule -DisplayName $FirewallName -ErrorAction SilentlyContinue
    if ($fw) {
        Remove-NetFirewallRule -DisplayName $FirewallName
        $done += "已删除防火墙规则 '$FirewallName'"
    }
    if ($done.Count -eq 0) { Write-Host "没有找到需要删除的共享/规则（可能已经清理过）。" -ForegroundColor DarkGray }
    else { $done | ForEach-Object { Write-Host "OK  $_" -ForegroundColor Green } }
    exit 0
}

# ---------- 参数补全 ----------
if ([string]::IsNullOrWhiteSpace($Account)) { $Account = "$env:USERDOMAIN\$env:USERNAME" }

if ([string]::IsNullOrWhiteSpace($Path)) {
    # 脚本放在 dsh-desktop\linux\vm-transfer\ 下，默认共享它的上一级 manager 目录
    $Path = Split-Path -Parent $PSScriptRoot
}
if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
    Write-Host "目录不存在: $Path" -ForegroundColor Red
    exit 3
}
$Path = (Resolve-Path -LiteralPath $Path).Path

# Hyper-V 虚拟交换机地址（给 Ubuntu 用的那个 IP）
$vmSwitchIp = $null
$addr = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -like '*Default Switch*' } |
        Select-Object -First 1
if ($addr) { $vmSwitchIp = $addr.IPAddress }

# ---------- 建共享 ----------
$existing = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Path -ne $Path) {
        Write-Host "共享 '$ShareName' 已存在但指向 '$($existing.Path)'，先删掉再重建..." -ForegroundColor Yellow
        Remove-SmbShare -Name $ShareName -Force
        $existing = $null
    }
}
if (-not $existing) {
    New-SmbShare -Name $ShareName -Path $Path -ReadAccess $Account -Description "DSH 发布文件 -> Hyper-V VM" | Out-Null
    Write-Host "OK  新建共享 \\$env:COMPUTERNAME\$ShareName  ->  $Path  (只读给 $Account)" -ForegroundColor Green
} else {
    Write-Host "OK  共享已存在：\\$env:COMPUTERNAME\$ShareName  ->  $Path" -ForegroundColor Green
    Grant-SmbShareAccess -Name $ShareName -AccountName $Account -AccessRight Read -Force -ErrorAction SilentlyContinue | Out-Null
}

# ---------- 防火墙：只放行 VM 网段的 445 ----------
$fw = Get-NetFirewallRule -DisplayName $FirewallName -ErrorAction SilentlyContinue
if ($fw) {
    Remove-NetFirewallRule -DisplayName $FirewallName
}
New-NetFirewallRule -DisplayName $FirewallName `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort 445 `
    -RemoteAddress $RemoteAddress -Profile Any `
    -Description "只允许虚拟机网段访问 SMB(445)，用于往 Hyper-V 里传发布包" | Out-Null
Write-Host "OK  防火墙：入站 445 仅允许 $RemoteAddress" -ForegroundColor Green

# ---------- 检查账号有没有密码（SMB 只认密码，PIN 不算） ----------
try {
    $u = Get-LocalUser -Name $env:USERNAME -ErrorAction Stop
    if ($u.PasswordRequired -eq $false -or -not $u.PasswordLastSet) {
        Write-Host ""
        Write-Host "注意：这个账号可能没有设置密码。SMB 只认账户密码（PIN/指纹/Windows Hello 都不行）。" -ForegroundColor Yellow
        Write-Host "      如果 VM 里挂载报 Permission denied，先给账号设个密码：Ctrl+Alt+Del -> 更改密码。"
    }
} catch {
    # 非管理员时读不到，忽略
}

# ---------- 打印给 Ubuntu 用的命令 ----------
$ip = if ($vmSwitchIp) { $vmSwitchIp } else { "172.22.144.1" }
$user = $env:USERNAME

Write-Host ""
Write-Host "================ 在 Ubuntu 虚拟机里执行 ================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  # 1) 装 CIFS 客户端"
Write-Host "  sudo apt-get install -y cifs-utils"
Write-Host ""
Write-Host "  # 2) 挂载（把密码写进 600 权限的文件，避免出现在 ps/历史里）"
Write-Host "  mkdir -p `$HOME/dsh-vm"
Write-Host "  sudo bash -c 'umask 077; printf ""username=$user`npassword=你的Windows密码`n"" > /etc/dsh-smb.cred'"
Write-Host "  sudo mount -t cifs //$ip/$ShareName `$HOME/dsh-vm \"
Write-Host "       -o credentials=/etc/dsh-smb.cred,vers=3.0,uid=`$(id -u),gid=`$(id -g),iocharset=utf8"
Write-Host ""
Write-Host "  # 3) 拷出来装"
Write-Host "  ls -l `$HOME/dsh-vm"
Write-Host "  cp `$HOME/dsh-vm/dsh-manager_1.0.0_all.deb ~/"
Write-Host "  sudo apt-get install -y ~/dsh-manager_1.0.0_all.deb"
Write-Host ""
Write-Host "  卸载共享（拷完后）: sudo umount `$HOME/dsh-vm"
Write-Host "  或直接跑本仓库的 vm-transfer/vm-mount.sh（帮你把上面串起来）"
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "提示：VM 里若 ping 不通 $ip，先确认 VM 还在 Hyper-V 的 Default Switch 上（VM 内 ip a 看是否有 172.22.x.x）。" -ForegroundColor DarkGray
Write-Host "撤销：powershell -ExecutionPolicy Bypass -File .\windows-share.ps1 -Remove" -ForegroundColor DarkGray
