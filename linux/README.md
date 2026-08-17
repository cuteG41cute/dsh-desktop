# DeepSeek Harness 桌面版（Linux）

把 DeepSeek Harness 的 WebUI 变成 deepin/Ubuntu/Debian 等 Linux 系统上的原生桌面窗口：
**GTK + WebKitGTK**，无浏览器、无控制台，双击即用。

与 Windows 版功能对齐：自动定位/启动 `dsh web` 服务、独立窗口、单实例、
关闭窗口自动停止本次启动的服务。

## 安装方式（二选一）

### 方式一：deb 安装包（推荐，deepin 可直接双击）

```bash
sudo apt install ./dsh-desktop_1.1.0_amd64.deb
```

安装后：
- 应用程序菜单出现 **DeepSeek Harness**；
- 命令行 `dsh-desktop` 可直接启动；
- 卸载：`sudo apt remove dsh-desktop`

### 方式二：通用 tarball（免 root，任意发行版）

```bash
tar xzf dsh-desktop-linux-1.1.0.tar.gz
cd dsh-desktop-linux
./install.sh          # 安装到 ~/.local/share/dsh-desktop
dsh-desktop           # 启动（或从应用菜单打开）
```

卸载：`~/.local/share/dsh-desktop/uninstall.sh`

## 依赖（首次启动自动引导安装）

首次运行启动器时会自动检查以下依赖，**缺失时询问你是否代为安装**：

| 依赖 | 自动安装方式 |
| --- | --- |
| python3 + python3-gi + WebKitGTK（4.1/4.0） | `sudo apt-get install`（deepin 图形会话会弹出授权框；`--setup` 可单独执行引导） |
| Node.js（dsh 需要 18+） | 自动下载 **Node.js 22 LTS 官方二进制**到 `~/.local/opt/node`（用户级，无需 root） |
| DeepSeek Harness（dsh） | `npm install -g @deepseek-ai/dsh`（无全局写权限时自动切换用户级 `~/.npm-global`） |

> 跳过询问/全自动：`DSH_NONINTERACTIVE=1 dsh-desktop`；
> 只做依赖引导不启动：`dsh-desktop --setup`。

## 使用

- 首次启动：自动检查/安装依赖（见上）→ 启动 dsh 服务（未运行则后台拉起）→ 打开桌面窗口；
- 依赖齐备后：直接开窗，无需任何网络或权限操作；
- 再次启动：服务已在运行时直接开窗；单实例（重复启动直接退出）；
- 关闭窗口：若服务是本启动器拉起的，会自动停止；
- 自定义端口：`DSH_WEB_URL=http://127.0.0.1:8080 dsh-desktop`

## 与 Windows 版的功能对照

| 功能 | 状态 |
| --- | --- |
| 多会话拖拽分离窗口（拖出侧边栏开新窗口） | ✅ 已支持（注入脚本 + WebKit 消息通道，逻辑与 Windows 版一致） |
| 单实例 | ✅（重复启动直接退出；Windows 版会唤起窗口，Linux 无此行为） |
| 手动指定 dsh 路径 | ✅ `DSH_BIN=/path/to/dsh/lib/bin.js dsh-desktop` |
| 系统托盘（X=最小化到托盘） | ⚠️ 无托盘（平台差异：Linux 关闭窗口即退出，服务随启动器停止） |
| 自动安装依赖与 dsh | ✅ 首次启动引导（见上文） |
| 图标/标题镜像/窗口内导航/端口跟随/日志 | ✅ 全部一致 |

> 差异说明：Linux 无系统托盘，主窗口关闭 = 退出程序（与 Windows「X=最小化到托盘」不同，
> 服务仍由启动器正确停止）；分离出的子窗口关闭只关自身。

## 目录结构

```
dsh-desktop.py      WebKitGTK 窗口程序
dsh-desktop         bash 启动器（服务检测/启动/清理）
install.sh          免 root 安装脚本
uninstall.sh        卸载脚本（安装时生成）
dsh-desktop.png     应用图标
```

## 已知问题

- **Deepin 密钥环弹窗**：首次启动时 WebKit 进程可能触发系统「解锁登录密钥环」提示，点解锁/继续即可，不影响使用；
- 交互类操作（关窗停服务/单实例/拖拽分离等）请在真实桌面环境验证。