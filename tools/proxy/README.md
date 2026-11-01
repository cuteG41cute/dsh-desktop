# 让虚拟机走本机代理（宿主 Windows → Hyper-V 里的 Linux）

目的：虚拟机的 `curl` / `apt` / `git` / **dsh-manager 的插件下载**都通过本机的代理出网。

## 为什么需要一个小中继

本机的代理（这台机器上是 `wandacloudCore.exe`）只监听 `127.0.0.1:7890`。
"127.0.0.1" 在虚拟机里指的是**虚拟机自己**，所以虚拟机连不到它。
又不想去改代理软件的「允许局域网连接」开关（那是它的配置，重置/升级会丢），
于是在 Hyper-V 网卡地址上开一个纯 TCP 转发：

```
虚拟机 172.22.148.197  ──▶  宿主机 172.22.144.1:7891  ──▶  127.0.0.1:7890（真代理）
```

`172.22.144.1` 是 Hyper-V Default Switch 的宿主地址（`Get-NetIPAddress` 里 `vEthernet (Default Switch)`）；
虚拟机里 `ip route` 的默认网关就是它。

## 本机（Windows）侧

```powershell
powershell -ExecutionPolicy Bypass -File tools\proxy\proxy-relay.ps1 -Install   # 开机自启 + 立即启动
powershell -ExecutionPolicy Bypass -File tools\proxy\proxy-relay.ps1 -Status
powershell -ExecutionPolicy Bypass -File tools\proxy\proxy-relay.ps1 -Uninstall # 撤销
```

- 日志：`%LOCALAPPDATA%\dsh-proxy\relay.log`
- 自启：启动文件夹里 `DSH-proxy-relay.lnk`
- 换地址：`-Install -Listen 0.0.0.0:7891` 或 `-Target 127.0.0.1:7890`
- 防火墙：Hyper-V 网段默认放行（实测虚拟机 4ms 就连上了，没加规则）

## 虚拟机（Ubuntu）侧

一次性写好（脚本在 `tools/host/vm-set-proxy.sh`，会先探测代理可用再写）：

| 落点 | 作用 |
| --- | --- |
| `~/.config/dsh-proxy.env` + `.bashrc`/`.profile` 里 source | 新开的 shell 里 `curl`/`git`/`npm` 走代理 |
| `/etc/apt/apt.conf.d/95proxy` | `apt-get` 走代理 |
| `git config --global http.proxy` | git 走代理 |
| `~/.config/environment.d/95-dsh-proxy.conf` | 图形界面（Plasma/Wayland → systemd user session）下次登录生效 |
| `systemctl --user set-environment ...` | 当前会话里新起的 GUI 进程立刻生效 |

撤销：

```bash
rm -f ~/.config/dsh-proxy.env ~/.config/environment.d/95-dsh-proxy.conf /etc/apt/apt.conf.d/95proxy
git config --global --unset http.proxy; git config --global --unset https.proxy
# 再把 .bashrc/.profile 里 "# dsh：走本机代理" 那段删掉
```

## 注意

- **虚拟机自己的 `127.0.0.1` 不受影响**（`no_proxy` 已经带 `localhost,127.0.0.1,...`），
  DSH WebUI、控制套接字、剪贴板桥都不受影响。
- 中继没起时，虚拟机里设了 `http_proxy` 的程序会直接失败（apt/curl 都会）。所以自启要装上；
  临时不用就 `-Stop`，或按上面「撤销」把虚拟机配置一起清掉。
- 代理只在本机回环上，中继只监听 Hyper-V 那一个网卡地址，等于"只有这台虚拟机能用"。

## 实测数据（2026-11-01）

| 从虚拟机发起 | 直连 | 通过代理 |
| --- | --- | --- |
| `https://api.github.com` | 200 | 200 |
| `https://raw.githubusercontent.com/...` | **000（失败）** | **200** |
| `https://codeload.github.com` | 301 | 301 |

也就是说：虚拟机能连上 GitHub API，但 **raw.githubusercontent.com 直连是废的** ——
这正是管理器"刷新不出新版本/新 tarball"的网络侧原因。
