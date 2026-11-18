# 找出 Hyper-V Default Switch 上 Linux 虚拟机的当前 IP（按 MAC 过滤）
# 用法: powershell -ExecutionPolicy Bypass -File tools\host\find-linux-vm.ps1

$ErrorActionPreference = 'Stop'

$addr = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -like '*Default Switch*' } |
    Select-Object -First 1

if (-not $addr) {
    Write-Host '找不到 Hyper-V Default Switch 网卡' -ForegroundColor Red
    exit 1
}

$ip = [string]($addr.IPAddress | Select-Object -First 1)
$prefix = ($ip.Split('.')[0..2] -join '.')
Write-Host ("NIC " + $addr.InterfaceAlias + " = " + $ip + "/" + $addr.PrefixLength + ", scanning " + $prefix + ".0/24 ...")

1..254 | ForEach-Object {
    $ping = New-Object System.Net.NetworkInformation.Ping
    $ping.Send("$prefix.$_", 80) | Out-Null
}

$hits = arp -a | Select-String '00-15-5d'
if (-not $hits) {
    Write-Host '没有找到 Hyper-V 虚拟机（可能没开机）' -ForegroundColor Yellow
    exit 1
}

foreach ($line in $hits) {
    $text = $line.Line.Trim()
    if ($text -match '^(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f-]+)') {
        $ip = $Matches[1]
        $mac = $Matches[2]
        $tcp = Test-NetConnection $ip -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue
        Write-Host ("{0,-16} {1}  ssh22={2}" -f $ip, $mac, $tcp)
    }
}
