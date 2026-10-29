# 在虚拟机里跑 Samba，让 Windows 把文件拷进去（这条路已在你的机器上跑通一半）

这条路线和你找的那篇 CSDN 教程一致：**Ubuntu 当 SMB 服务端，Windows 当客户端**，
在 Windows 资源管理器里把 `.deb` 拖进虚拟机的共享目录。好处是**完全不需要 Windows 管理员权限**。

## 已经确认的现状（我在宿主机实测）

| 检查项 | 结果 |
|---|---|
| 虚拟机 IP | `172.22.148.197`（DHCP，会变） |
| 139 端口 | **OPEN** ✅ |
| 445 端口 | **OPEN** ✅ |

139/445 都开着，说明 `smbd` 已经在跑、`ufw allow samba` 也已生效。
所以你**只剩“登录凭据”这一步**——也就是卡住的那个“添加允许登录的 samba 用户”。

## 卡点的三个真实原因

### 原因 1：文章里的 `pdbedit -a [username]` 写法是错的（最常见）

`pdbedit` 加用户必须带 `-u`：

```bash
# 错（教程里这么写，会报 usage / invalid option）
sudo pdbedit -a user0

# 对
sudo pdbedit -a -u user0
```

`smbpasswd` 那行才是直接跟用户名：`sudo smbpasswd -a user0`。
两者等价，任选一个，**推荐 `smbpasswd`**（会交互式让你输两遍密码，不易出错）。

### 原因 2：用户名必须等于 **Linux 系统里已存在**的用户

`sudo pdbedit -L` 加不进去、报 `Failed to add entry for user xxx` 时，基本都是这个：
用了 **Windows 的用户名**（比如 `twinblade`），而 Ubuntu 里并没有这个系统用户。

先确认自己的 Linux 用户名：

```bash
id -un        # 例如 ubuntu / user0 / deepin
```

然后用**这个**名字：

```bash
sudo smbpasswd -a "$(id -un)"
```

> 如果你就是想用 `twinblade` 这个名字，得先建系统用户（无家目录也能用）：
> ```bash
> sudo useradd -M -s /usr/sbin/nologin twinblade
> sudo smbpasswd -a twinblade
> ```

### 原因 3：`smb.conf` 里的 `valid users` 和加进去的用户名不一致

加了用户但连不上/提示无权限，通常是 `valid users = user0` 写的名字和实际 samba 用户不同。
把共享段改成你自己的名字（和 `id -un` 一致），例如：

```ini
[share]
  comment = File share
  path = /home/<你的用户名>/share
  available = yes
  browseable = yes
  valid users = <你的用户名>
  read only = no
  writable = yes
  create mask = 0775
  directory mask = 0775
```

改完**必做**：

```bash
sudo testparm -s                 # 语法检查，看有没有报错
sudo systemctl restart smbd      # 必须重启才生效
sudo pdbedit -L                  # 应能看到你的用户名
ls -ld ~/share                   # 属主应是你：sudo chown -R $(id -un):$(id -un) ~/share
```

## 一条命令看全诊断信息

粘进虚拟机跑，输出贴给我我就能定位：

```bash
{ id -un; id; echo '--- samba users ---'; sudo pdbedit -L;
  echo '--- share def ---'; sudo testparm -s 2>/dev/null | grep -A8 '^\[' ;
  echo '--- service ---'; systemctl is-active smbd nmbd;
  echo '--- dir ---'; ls -ld ~/share 2>&1; } 2>&1
```

## 从 Windows 连进去

资源管理器地址栏：`\\172.22.148.197\share`（`share` 换成你 `smb.conf` 里的段名）。

- 弹框用户名填 `172.22.148.197\<你的用户名>` 或直接 `<你的用户名>`，密码是 **samba 密码**（`smbpasswd` 时设的，不是 Linux 登录密码）。
- 提示“不允许一个用户使用一个以上用户名”或一直用旧密码 → 清掉缓存再连：

```powershell
net use * /del /y
cmdkey /list          # 有旧的 172.22.148.197 条目就删掉，或去「凭据管理器」删
```

- VM 的 IP 重启会变：在 VM 里 `ip a | grep 172.22`，或宿主 `Get-NetNeighbor -AddressFamily IPv4 | ? IPAddress -like '172.22.*'`。

## 拷进去之后

Windows 里把 `dsh-manager_1.0.0_all.deb` 拖进那个共享目录，然后在虚拟机里：

```bash
ls -l ~/share
sha256sum ~/share/dsh-manager_1.0.0_all.deb    # 应为 8006149220ba531a8b9792a98db7a9c40ef1a4ede0c38f120790caaf4a832736
sudo apt-get install -y ~/share/dsh-manager_1.0.0_all.deb
dsh-manager --headless list                    # 冒烟
```

用完想收窄暴露面：`sudo systemctl stop smbd`（或 `sudo ufw delete allow samba`）。

## 和另一条路（Windows 建共享）的取舍

| | 本文件：VM 里跑 Samba | `README.md`：Windows 建共享 |
|---|---|---|
| Windows 管理员权限 | **不需要** | 需要一次 UAC |
| 谁发起 | Windows 拉（资源管理器拖拽，直观） | VM 拉（`mount.cifs`，脚本化） |
| IP 稳定性 | VM 的 IP 会变，要跟着改 | 宿主 IP 固定 `172.22.144.1` |
| 文件方向 | 只能往共享目录里放 | 共享整个 Windows 目录，VM 里只读/可写取决于配置 |
