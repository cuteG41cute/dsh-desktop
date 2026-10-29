# 用 SMB 把文件传进 Hyper-V 虚拟机

把 Windows 上编译好的东西（比如 `dsh-manager_1.0.0_all.deb`）通过 **SMB / 局域网共享** 送进
Hyper-V 里的 Ubuntu 虚拟机，然后正常 `apt install`。

> 这条路能用，而且比 HTTP 临时服务器更"正规"：传完就是一个目录，能反复用、能放多个文件、能校验 sha256。
> 唯一的前提是 **Windows 侧需要一次管理员（UAC）操作** 来建共享 + 放行 445，原因见下。

---

## 0. 为什么必须一次管理员

SMB 通信只需要两样东西：

| 要素 | 你这台机器的实测状态 |
|---|---|
| 服务端进程 | `LanmanServer` **Running**（自动启动）✅ |
| 445 端口监听 | `::` 上 **Listen** ✅ |
| 共享目录 | 只有 `C$` / `ADMIN$` / `IPC$`，**都是管理共享** |
| 连接管理共享的权限 | 需要 **Administrators 组**；当前账号 `twinblade` 不在里面 ❌ |
| 445 入站防火墙 | 需要在 VM 来源上放行（建规则要管理员） |

管理共享（`C$` 之类）虽然"现成"，但只有管理员组能连，所以对普通账号无效。
**建一个普通共享**是唯一干净的办法，而 `New-SmbShare` 必须提权——这就是那一次 UAC 的全部原因。

---

## 1. Windows 侧：建共享（一次，约 10 秒）

### 方式 A（推荐）：跑脚本

在资源管理器里找到 `dsh-desktop\linux\vm-transfer\windows-share.ps1`，
**右键 →「使用 PowerShell 运行」**。

这一步**不会**自动提权（Windows 的“使用 PowerShell 运行”和双击一样是非管理员上下文），
所以脚本自己会弹一次 UAC 并重开一个**管理员的、不会自动关闭**的 PowerShell 窗口继续干活。
弹窗点「是」即可；点「否」它会给出提示并等你按回车，不会闪退。

> 只想看它打算干什么、不动系统：加 `-DryRun`，它会打印提权后要执行的完整命令行然后退出。
> ```powershell
> powershell -ExecutionPolicy Bypass -File .\windows-share.ps1 -DryRun
> ```

它做三件事，全部可撤销：

1. 建共享 `DSH-VM` → 默认指向 `dsh-desktop\linux\manager\`（`.deb` 所在目录），只给当前账号**只读**；
2. 建入站防火墙规则 `DSH VM share (SMB 445)`，**只**放行来源 `172.22.144.0/20`（Hyper-V Default Switch 网段）的 445；
3. 在窗口里打印 Ubuntu 那边该敲的命令。

想换个目录共享：

```powershell
powershell -ExecutionPolicy Bypass -File .\windows-share.ps1 -Path "D:\builds"
```

撤销（删共享 + 删规则）：

```powershell
powershell -ExecutionPolicy Bypass -File .\windows-share.ps1 -Remove
```

### 方式 B：两条命令手动来

管理员 PowerShell 里：

```powershell
# 1) 建共享，只读给当前账号
New-SmbShare -Name DSH-VM -Path "C:\Users\twinblade\Documents\deeepseek harness\dsh-desktop\linux\manager" -ReadAccess "$env:USERDOMAIN\$env:USERNAME"

# 2) 只对虚拟机网段放行 445
New-NetFirewallRule -DisplayName "DSH VM share (SMB 445)" -Direction Inbound -Action Allow `
  -Protocol TCP -LocalPort 445 -RemoteAddress 172.22.144.0/20 -Profile Any
```

> **别图省事把 445 对 `Any` 全开**：那等于把文件共享暴露给咖啡厅 WiFi 上的所有人。限定来源网段只多打十几个字符。

### 前提：Windows 账号必须有**密码**

SMB 只认账户密码。**PIN、指纹、Windows Hello 都不算**。如果只设过 PIN：

- `Ctrl + Alt + Del` → 更改密码（给账号设一个真密码），或
- 管理员窗口：`net user twinblade *`

如果是 **Microsoft 账号**登录的：用户名填**邮箱**，密码填**微软账号密码**（不是 PIN）。

---

## 2. Ubuntu 侧：挂载 + 拷贝 + 安装

主机地址：Hyper-V Default Switch 上网关就是 Windows，你这台是 **`172.22.144.1`**（脚本会自动认）。
实测这台的虚拟机在 `172.22.148.197`（DHCP，会变；VM 里 `ip a` 可看，宿主上 `Get-NetNeighbor` 也能查）。

### 一行版（用仓库里的脚本）

```bash
# 先确认能通
ping -c1 172.22.144.1

# 挂载到 ~/dsh-vm 并列出内容（第一次会问 Windows 密码）
DSH_SMB_HOST=172.22.144.1 DSH_SMB_SHARE=DSH-VM DSH_SMB_USER=twinblade ./vm-mount.sh

# 挂载 + 把共享里的 *.deb 拷到 ~/
./vm-mount.sh --copy

# 挂载 + 拷贝 + 直接 apt install
./vm-mount.sh --install

# 用完卸载
./vm-mount.sh --umount
```

脚本会把密码写进 `/etc/dsh-smb.cred`（权限 600），避免密码出现在 `ps`、shell 历史、`mount` 输出里。

### 全手动版（知道每步在干什么）

```bash
sudo apt-get update && sudo apt-get install -y cifs-utils

mkdir -p ~/dsh-vm

# 凭据文件，别用 -o password=xxx（会进 ps 和历史）
sudo bash -c 'umask 077; printf "username=twinblade\npassword=你的密码\n" > /etc/dsh-smb.cred'

sudo mount -t cifs //172.22.144.1/DSH-VM ~/dsh-vm \
     -o credentials=/etc/dsh-smb.cred,vers=3.0,uid=$(id -u),gid=$(id -g),iocharset=utf8

ls -l ~/dsh-vm
cp ~/dsh-vm/dsh-manager_1.0.0_all.deb ~/
sha256sum ~/dsh-manager_1.0.0_all.deb   # 应与 80061492...4a832736 一致
sudo apt-get install -y ~/dsh-manager_1.0.0_all.deb
```

挂载参数逐个解释：

| 参数 | 作用 |
|---|---|
| `vers=3.0` | SMB3；Windows 11 已禁用 SMB1/来宾，必须 3.x |
| `credentials=` | 从 600 权限文件读账号密码 |
| `uid=$(id -u),gid=$(id -g)` | 让挂上来的文件属主是**你**，不用 sudo 就能读 |
| `iocharset=utf8` | 中文文件名不乱码（传中文名文件时必要） |
| `ro`（可选） | 强制只读，纯传文件更安全 |

### 不想装 mount：用 `smbclient` 直接拉

```bash
sudo apt-get install -y smbclient
smbclient //172.22.144.1/DSH-VM -U twinblade
# smb: \> ls
# smb: \> get dsh-manager_1.0.0_all.deb
# smb: \> quit
```

图形界面（装了 Nautilus）：地址栏输入 `smb://172.22.144.1/DSH-VM`，输入账号密码即可。

---

## 3. 出错了对照这张表

| 现象 | 原因 | 处理 |
|---|---|---|
| `mount error(115): Operation now in progress` / 连不上 | VM 和 Windows 不在同一网段，或 445 被防火墙挡 | VM 里 `ip a` 要有 `172.22.x.x`；Windows 上确认脚本里的防火墙规则存在；`Test-NetConnection 172.22.144.1 -Port 445` |
| `mount error(13): Permission denied` | 账号/密码错，**或账号没设密码**，或用了 PIN | 用真密码；Microsoft 账号要用邮箱+MS 密码 |
| `mount error(2): No such file or directory` | 共享名写错（大小写无关，但拼错常见） | Windows 上 `Get-SmbShare` 看准确名字 |
| `mount error(112): Host is down` | SMB1 被禁 / 协商失败 | 加 `vers=3.0`（或 `3.1.1`） |
| `mount error(95): Operation not supported` | 服务端强制 SMB 签名（你这台就是 `True`），老内核/cifs-utils 协商失败 | 用 `vers=3.1.1`；并把 cifs-utils 升到新版 |
| 挂上去了但写不进去 | 脚本给的是**只读**共享 | 改用 `-FullAccess` 重建，或本来就不需要写 |
| 文件名乱码 | 缺 `iocharset=utf8` | 加该参数重挂 |
| `sudo: a password is required` 之类 | 脚本里 sudo 没交互 | 手动执行或先 `sudo -v` |

安全提醒：`/etc/dsh-smb.cred` 里是明码密码（600 权限）。传完文件可以删掉它并 `-Remove` 撤销共享。

---

## 4. 为什么不建议"反过来"（VM 里装 Samba，让 Windows 去拉）

技术上可行——实测宿主 ping 得通虚拟机的 `172.22.148.197`（ICMP 通，说明 Default Switch 上宿主和客体
就在同一个 /20 二层网段，宿主 → 客体入站并不被阻断）。但这条路有三个实际的麻烦：

1. **VM 的 IP 是 DHCP**，宿主重启后会变（实测就那么漂过），每次都要重新确认地址；
2. 客体还要 `ufw allow 445` + 装 `samba` + `smbpasswd -a` 建账号，步骤比 Windows 侧建共享多；
3. 要从 Windows 发起 `copy \\172.22.x.x\share`，脚本里得写死可变 IP。

所以方向反过来是"能做但不好维护"。传文件这个场景，共享建在 Windows 侧（本文件的方案）更省事。

> 补充实测：这台机器的 SMB 服务端 `RequireSecuritySignature = True`（Windows 11 24H2 起的默认）。
> Linux `mount.cifs` 的 SMB3 支持签名协商，一般无感；若真在协商阶段失败，用 `vers=3.1.1` 重试。

---

## 5. 连管理员都不想动？还有三条路

| 方案 | 代价 | 备注 |
|---|---|---|
| **临时 HTTP 服务** | 也需要一次管理员：`New-NetFirewallRule -LocalPort 8765` | 只需一行；仓库旁边那个 8765 就是这样起的 |
| **GitHub / 镜像站** | 无 | 把 `.deb` 推到仓库，VM 里 `curl -LO https://.../raw/main/...`；本机到 GitHub 的 HTTPS 在当前网络被挡过，需代理或镜像 |
| **Hyper-V 增强会话** | VM 里要装 `xrdp` + `linux-image-virtual`（需要 apt，网络已通） | 装好后能直接**拖拽文件 / 复制粘贴**，体验最好，但是一次性配置较重 |

---

## 文件清单

| 文件 | 跑在哪 | 作用 |
|---|---|---|
| `windows-share.ps1` | Windows（自动提权） | 建/删共享 + 只对 VM 网段放行 445，并打印挂载命令 |
| `vm-mount.sh` | Ubuntu 虚拟机 | 装 cifs-utils、挂载、拷贝 `.deb`、可选直接安装 |
| `samba-in-vm.md` | — | **另一条路**：VM 里跑 Samba、Windows 拖文件进去，不需要任何管理员权限 |
| `README.md` | — | 本文 |
