# 虚拟机检查点回滚后的恢复清单

> 结论先说：**代码没有丢。** 所有源码、全部 12 个 deb、交接包、插件包都在**这台 Windows 主机上**，
> 并且已经 `git push` 到 GitHub（`cuteG41cute/dsh-desktop`、`cuteG41cute/dsh-screenshot`）。
> 丢的是**虚拟机内部的状态**（装了哪些包、实例里被改过的文件、共享盘里我传过去的那些副本）。
> 虚拟机的检查点回滚不会影响主机上的任何文件。

---

## 0. 现在的实际状况（刚探测的）

| 探测 | 结果 | 含义 |
| --- | --- | --- |
| `ping 172.22.148.197` | ✅ 通 | 虚拟机是开着的 |
| SMB 445 / 139 | ❌ 关闭 | **Samba 没起来**（共享盘因此打不开） |
| `3080`（dsh web） | ❌ 关闭 | DSH 服务没在跑 |
| `8099`（桥） | ❌ 关闭 | 手机桥没在跑（本来就是 Windows 上的，另说） |

所以第一步不是"找文件"，是**把共享盘叫回来**（见 §1）。共享盘一通，剩下的事我这边一键就能推回去。

---

## 1. 第一件事：把共享盘修回来（虚拟机里执行）

```bash
# 看看 samba 装了没有、服务在不在
dpkg -l | grep -E '^ii\s+samba\s' || echo "samba 没装"
systemctl status smbd --no-pager | head -n 5

# 起服务（最可能就是这个：回滚后没开机自启）
sudo systemctl enable --now smbd

# 没装的话：
# sudo apt update && sudo apt install -y samba
```

如果 `smbd` 起来了但共享目录/账号丢了（回滚把 `/etc/samba/smb.conf` 也带回去了），
最小可用配置（把 `~/share` 共享出来）：

```bash
sudo tee /etc/samba/smb.conf >/dev/null <<'EOF'
[global]
   workgroup = WORKGROUP
   server string = DSH share
   map to guest = Bad User
   server min protocol = SMB2

[share]
   path = /home/twinblade/share
   browseable = yes
   read only = no
   guest ok = yes
   create mask = 0664
   directory mask = 0775
EOF

mkdir -p ~/share
sudo systemctl restart smbd smbd 2>/dev/null || sudo systemctl restart smbd
```

然后在 Windows 上验证：`cmd /c dir \\172.22.148.197\share` 能列出来就通了。

---

## 2. 我这边会推回去的东西（共享盘一通就恢复）

| 文件 | 是什么 | 恢复后的用途 |
| --- | --- | --- |
| `dsh-manager_1.3.2_all.deb` | 最新管理器（7 主题 × 日/夜） | `sudo dpkg -i` 装回去 |
| `dsh-manager-ui-redesign.tar.gz` | 交接包（设计稿 + 源码 + 任务书 + 参考图 15 张） | 解包继续 UI 复刻任务 |
| `dsh-screenshot-1.3.1.tar.gz` | 截图插件（含原生截屏桥） | 用管理器「管理插件」本地导入 |
| `install-deb.sh` | 装/升级管理器（自动挑最新 deb + 校验） | `cd ~/share && bash install-deb.sh` |
| `README-*.txt` | 前几轮的说明 | 备查 |

主机上的完整清单（`recovery/`）：上面这些 + 历史版本 deb（1.1.2 … 1.3.2，共 12 个）。

---

## 3. 虚拟机里需要重做的事（从快照回滚必然要重来）

按顺序：

1. **装管理器**：`cd ~/share && bash install-deb.sh` → 关掉旧窗口重开；
2. **装截图插件 1.3.1**：管理器「管理插件…」→ 本地导入 `dsh-screenshot-1.3.1.tar.gz`，
   或从 GitHub main 更新（仓库 HEAD 已含 `nativeCapture`）；
3. **桌面壳补丁**：管理器「打开窗口」时会自动把 `share/dsh-desktop.py` 同步到各实例
   （原生截屏桥在里面），不用手动打补丁。验证：`grep -c _native_screenshot <实例>/share/dsh-desktop.py`；
4. **截图工具**（要截图比对的话）：`sudo apt install -y spectacle imagemagick python3-pil`；
5. **DSH 服务**：管理器里点「启动服务」，或 `dsh-manager --headless start --prefix <实例>`；
6. 其它按需：`fonts-inter`、`librsvg2-common`、`python3-cairo`、`python3-gi-cairo`（UI 攻坚要用）。

---

## 4. 怎么确认"真的恢复了"

```bash
dpkg-query -W -f='${Version}\n' dsh-manager          # 期望 1.3.2
grep -c _native_screenshot ~/Program/deepseek-harness-1/share/dsh-desktop.py   # 期望 >= 1
python3 -c "import json,glob;print(open(glob.glob('$HOME/share/*manager*.deb')[0],'rb').read(8))"
dsh-manager --version
```

界面侧：打开管理器 → 顶栏「毛玻璃 ▾」能换 7 套主题、日/夜能切换、左侧实例行有头像与状态点。

---

## 5. 为什么这次几乎没损失（以后也照这个做）

| 层 | 存在哪 | 会不会被快照回滚影响 |
| --- | --- | --- |
| 源码 + 文档 | 主机工作区 + **GitHub** | 不会 |
| 构建产物（12 个 deb） | 主机的 `dsh-desktop/linux/manager/*.deb` | 不会 |
| 交接包 / 插件包 | 主机 `.tmp/`、`recovery/` | 不会 |
| 设计稿 | 主机 `Documents\kimi\workspace\ui-redesign` | 不会 |
| 虚拟机内部状态（装了什么、实例里的 diff、`~/share`） | 虚拟机磁盘 | **会**（这次就是） |

所以规矩是：**任何"只存在于虚拟机里"的东西，都要么 push 到 GitHub，要么回传到主机。**
如果你在虚拟机里改过 `share/dsh-desktop.py` 之类，改完把文件拷回 `~/share`，我这边就能拉回主机留档。

---

## 6. 如果共享盘一时修不好（备用通道）

主机上可以起一个只读 HTTP 服务，虚拟机上用 `curl` 拉（不依赖 Samba）：

```powershell
# 主机（Windows）执行：在 recovery/ 目录起服务
cd "C:\Users\twinblade\Documents\deeepseek harness\recovery"
python -m http.server 8000 --bind 0.0.0.0
```

```bash
# 虚拟机里拉（主机 IP 172.22.144.1）
mkdir -p ~/share && cd ~/share
curl -O http://172.22.144.1:8000/dsh-manager_1.3.2_all.deb
curl -O http://172.22.144.1:8000/install-deb.sh
bash install-deb.sh
```

如果 Windows 防火墙拦了入站 8000，会看到 `curl: (7) Failed to connect`——那就还是走 §1 修 Samba。
---

## 附：2026-10-31 实际恢复结果（SSH 可用后亲自操作）

**回滚把 VM 的 $HOME 退回到了 10/19-20 的全新状态**：没有 `~/Program/*`、没有 `~/.dsh`、
没有 node/npm、没有 `~/.config/dsh-manager`、没有 Samba 配置、没有截图/比对工具。
唯一还在的是今天新装的 dsh-manager（`~/share` 里那两个文件）。

已通过 SSH 重建（**不需要 Samba**）：

| 项 | 结果 |
| --- | --- |
| 实例 1 | `/home/twinblade/Program/deepseek-harness-1`，dsh 0.2.1-rc.5 / node 26.13.0 / 3080 / **运行中** |
| 实例 2 | `~/.local/opt/deepseek-harness-2`，同版本 / 3081 / 已装（未启动） |
| 桌面壳 | 两个实例的 `share/dsh-desktop.py` 都含原生截屏桥（`_native_screenshot` ×3） |
| 截图插件 | dsh-screenshot **1.3.1** 已导入实例 1，boot 图谱里能查到 |
| 管理器 | 装的是 1.3.2；**1.3.3 已放到 `~/share`**（修了下面两个 bug），需 sudo 安装 |

重建过程中的两个坑（已在 1.3.3 修掉，并加了 gate `tools/plugin-import-check.py`）：

1. **空数组占位符**：新 profile 的 `cordis.patch.yml` 里是裸 `[]`，插件安装器往后面追加
   `- insert:` → YAML 变成两个文档 → `dsh web` 启动即失败
   （`end of the stream or a document separator is expected`）。
   现场已手工修好（原文件备份在 `cordis.patch.yml.bak-empty-array`），1.3.3 起自动处理。
2. **平铺 tar.gz**：包里直接是 `package.json + lib/` 时，安装器把 `lib/` 当包根，
   报"没找到带 name 的 package.json"。1.3.3 起两种打包方式都支持。

**还需要你跑一次 sudo**（工具链 + Samba + 管理器 1.3.3 一起搞定）：

```bash
sudo bash ~/share/fix-vm-sudo.sh
```

跑完 Windows 上 `cmd /c dir \\172.22.148.197\share` 就能用了。