# 从这台 Windows 电脑用 SSH 控制 Linux 虚拟机

> 适用环境（2026-11 实测）：
> - 宿主机：Windows 11，自带 OpenSSH 客户端 `C:\WINDOWS\System32\OpenSSH\ssh.exe`
> - 虚拟机：Ubuntu 26.04.1 LTS，主机名 `twinblade-Virtual-Machine`，用户 `twinblade`
> - 网络：Hyper-V **Default Switch**（宿主机侧 `172.27.240.1/20`，虚拟机在 `172.27.x.x`）
> - 认证：已配置密钥登录（`~/.ssh/id_ed25519`），虚拟机内 `sudo` 免密码

---

## 1. 第一步：找到虚拟机当前的 IP

Default Switch 是 DHCP，**虚拟机每次重启 IP 可能变化**。三种找法，从快到慢：

### 方法 A：看虚拟机控制台（最可靠）

Hyper-V 窗口里登录后执行：

```bash
hostname -I
```

### 方法 B：在 Windows 上用一句 PowerShell 扫出来

```powershell
# 扫当前 Default Switch 网段的 /24，找出 MAC 为 00-15-5d-* 的 Hyper-V 虚拟机
$subnet = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object InterfaceAlias -like '*Default Switch*').IPAddress.Split('.')[0..2] -join '.'
1..254 | ForEach-Object {
  $p = New-Object System.Net.NetworkInformation.Ping
  $p.Send("$subnet.$_", 80) | Out-Null
}
arp -a | Select-String '00-15-5d' | ForEach-Object { $_.Line.Trim() }
```

输出形如 `172.27.250.97  00-15-5d-01-02-01  static`，第一个字段就是 IP。

> 仓库里也提供了一个封装好的脚本：`tools/host/find-linux-vm.ps1`，直接跑 `powershell -File tools/host/find-linux-vm.ps1` 即可。

### 方法 C：给虚拟机配固定 IP（一劳永逸，但注意网段会变）

在虚拟机里编辑 netplan（Ubuntu 26.04 路径通常是 `/etc/netplan/*.yaml`）：

```yaml
network:
  version: 2
  ethernets:
    eth0:                       # 用 `ip a` 确认网卡名
      dhcp4: false
      addresses: [172.27.250.97/20]
      routes:
        - to: default
          via: 172.27.240.1
      nameservers:
        addresses: [223.5.5.5, 1.1.1.1]
```

```bash
sudo netplan apply
```

⚠️ **注意**：Hyper-V Default Switch 的网段在宿主机重启后**有可能变化**（例如从 `172.27.x` 变到 `172.30.x`）。网段一变，固定 IP 就失联了。真要长期稳定，建议在 Hyper-V 里新建一个 **Internal/External 虚拟交换机**并固定网段，或改用桥接。

---

## 2. 连接

```powershell
ssh twinblade@172.27.250.97
```

首次连接会提示确认主机指纹，输入 `yes`。

### 配置免密登录（如果换过密钥或新装系统）

Windows 侧：

```powershell
type $HOME\.ssh\id_ed25519.pub | ssh twinblade@<VM_IP> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

> Windows 没有 `ssh-copy-id`，上面这条管道就是等价做法。

### 建议写进 `~/.ssh/config`（可选但省事）

```sshconfig
Host vm
  HostName 172.27.250.97
  User twinblade
  Port 22
  ServerAliveInterval 30
  ServerAliveCountMax 3
```

之后直接 `ssh vm`、`scp 文件 vm:/tmp/` 都行。**IP 变了记得改这里**。

---

## 3. 日常命令速查

| 目的 | 命令 |
| --- | --- |
| 登录 | `ssh twinblade@<IP>` |
| 只跑一条命令 | `ssh twinblade@<IP> "uptime && free -h"` |
| 上传文件 | `scp -P 22 .\本地文件.zip twinblade@<IP>:/tmp/` |
| 下载文件 | `scp -P 22 twinblade@<IP>:/tmp/结果.deb .\` |
| 整目录同步 | `tar -czf - .\dir \| ssh twinblade@<IP> "tar -xzf - -C ~/dir"` |
| 远程执行 sudo | `ssh twinblade@<IP> "sudo -n apt-get install -y ffmpeg"`（已配 NOPASSWD） |
| 看图形会话 | 直接看 Hyper-V 窗口（SSH 只是命令行 |

### 端口转发（在本机浏览器里访问虚拟机里的服务）

```powershell
# 把虚拟机的 8092（audio.cpp 本地语音）映射到本机 18092
ssh -N -L 18092:127.0.0.1:8092 twinblade@<IP>

# 管理器仪表盘 8097
ssh -N -L 18097:127.0.0.1:8097 twinblade@<IP>
```

然后本机浏览器打开 `http://127.0.0.1:18092/v1/models` 就能看到虚拟机上跑的服务。

---

## 4. 这台机器上常用的运维动作

```bash
# 安装/升级管理器 deb
scp -P 22 .\dist\linux\dsh-manager_*.deb twinblade@<IP>:/tmp/
ssh twinblade@<IP> "sudo -n dpkg -i /tmp/dsh-manager_*.deb"

# 以「本地语音」页直接启动管理器（调试用）
ssh twinblade@<IP> "pkill -f /usr/bin/dsh-manager; \
  DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 \
  DSH_MANAGER_START_PAGE=tts setsid nohup /usr/bin/dsh-manager >/tmp/mgr.log 2>&1 &"

# 重启图形会话（改分辨率/缩放后）
ssh twinblade@<IP> "sudo -n systemctl restart sddm"

# 看日志
ssh twinblade@<IP> "tail -50 ~/.config/dsh-manager/crash.log 2>/dev/null; \
  tail -20 ~/.local/share/dsh-manager/services/audiocpp/logs/server.log 2>/dev/null"

# 截图（GNOME 的 portal，存到 ~/图片/Screenshot.png）
ssh twinblade@<IP> "gdbus call --session --dest org.freedesktop.portal.Desktop \
  --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Screenshot.Screenshot '' '{}'"
```

> 截图和 GUI 操作需要 `XDG_RUNTIME_DIR=/run/user/1000` 与 `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`，否则会报 “cannot connect to session bus”。

---

## 5. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `connect to host ... port 22: Connection timed out` | IP 变了（最常见）或虚拟机没开机。用第 1 节的方法重新找 IP |
| `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED` | 虚拟机重装/换 IP 导致指纹变化。执行 `ssh-keygen -R <IP>` 清掉旧记录 |
| `Permission denied (publickey)` | 公钥没写进虚拟机 `~/.ssh/authorized_keys`，按第 2 节重新追加 |
| 命令里带 `sudo` 卡住 | 这台 VM 已配 NOPASSWD；若换机器，用 `ssh -t` 分配终端 |
| `apt` 报连不上 `172.22.x.x:7891` | 虚拟机里残留了旧网段的 apt 代理配置：`sudo mv /etc/apt/apt.conf.d/95proxy /etc/apt/apt.conf.d/95proxy.disabled` |
| 想跑 GUI 程序但黑屏 | SSH 不带图形；用 Hyper-V 窗口，或 `ssh -X` + 本机 X server（更麻烦） |

---

## 6. 安全提醒

- **不要**把这台 VM 的 22 端口通过隧道/路由器映射到公网；它只是本地开发机。
- `~/.ssh/id_ed25519` 是私钥，不要提交到仓库、不要发给别人。
- 虚拟机里的 `sudo` 是免密的，任何能 SSH 进来的人都能拿 root——局域网自用可以，多人环境要改回密码验证。
- 不再需要某台机器的免密时，直接编辑虚拟机 `~/.ssh/authorized_keys` 删掉对应行。

---

## 7. 附：本次会话里实际用过的连接参数

```
IP       172.27.250.97（会变）
Port     22
User     twinblade
OS       Ubuntu 26.04.1 LTS
Hostname twinblade-Virtual-Machine
```
