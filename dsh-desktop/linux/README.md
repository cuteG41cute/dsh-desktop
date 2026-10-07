# DeepSeek Harness 桌面版（Linux）

把 DeepSeek Harness 的 WebUI 变成 deepin/Ubuntu/Debian 等 Linux 系统上的原生桌面窗口：
**GTK + WebKitGTK**，无浏览器、无控制台，双击即用。

与 Windows 版功能对齐：自动定位/启动 `dsh web` 服务、独立窗口、单实例、
关闭窗口自动停止本次启动的服务。

## 安装方式（二选一）

### 方式一：deb 安装包（推荐，deepin 可直接双击）

```bash
sudo apt install ./dsh-desktop_1.2.4_amd64.deb
```

安装后：
- 应用程序菜单出现 **DeepSeek Harness**；
- 命令行 `dsh-desktop` 可直接启动；
- 卸载：`sudo apt remove dsh-desktop`

### 方式二：通用 tarball（免 root，任意发行版）

```bash
tar xzf dsh-desktop-linux-1.2.4.tar.gz
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

## dsh 版本与 Web 认证（dsh ≥ 0.1.5）

从 **dsh 0.1.5** 起，WebUI 增加了浏览器认证：

- 未认证访问 `http://127.0.0.1:3080/` 返回 **401**（正文提示 `dsh web authentication required`）；
- `dsh web` 启动时会打印一条带一次性 token 的地址（`http://127.0.0.1:3080/?token=…`），
  用它访问一次即可换取一枚最长 30 天有效的签名 cookie；
- `dsh web` 默认还会打开系统浏览器，桌面版启动时必须加 `--no-open`。

本启动器已适配这套认证，**不需要用户手动做任何事**：

1. 服务没在运行时用 `dsh web --no-open` 启动；
2. 探测服务时把「200」和「401 + dsh 认证提示」都视为“服务已在运行”；
3. 取得认证凭据，按可靠性依次尝试：
   - **自行签发 cookie**：签名密钥是持久的（`$DSH_HOME/.credentials.yaml` 的
     `client-connection/browser-session` 记录），启动器按 dsh 的格式签发一枚 cookie，
     再用真实 HTTP 请求确认服务端接受它，然后把 cookie 交给窗口注入 ——
     因此**即使 WebUI 是你在别处手动启动的（读不到 token 日志）也能正常认证**；
   - 退回**认证 URL**：从启动日志里取 `dsh web: http://…?token=…`，直接用该地址开窗；
   - 都没有：照旧打开原地址（配置里已有有效 cookie 时仍可正常显示）。
4. 窗口发现页面是「需要认证」时会写入 cookie 并自动刷新一次（WebKitGTK 没有可移植的
   cookie 写入接口，因此用 JS 方式，逻辑见 `dsh-desktop.py`）。

> 说明：认证参数由 dsh 决定。若将来 dsh 改了密钥存放或 cookie 格式，验证会失败并自动
> 退回认证 URL 方式；再不行窗口会显示 401 页面，此时按页面提示用 `dsh web` 打印的
> 带 token 地址打开一次即可。

## 与 Windows 版的功能对照

| 功能 | 状态 |
| --- | --- |
| 多会话拖拽分离窗口（拖出侧边栏开新窗口） | ✅ 已支持（注入脚本 + WebKit 消息通道，逻辑与 Windows 版一致） |
| 单实例 | ✅（重复启动直接退出；Windows 版会唤起窗口，Linux 无此行为） |
| 手动指定 dsh 路径 | ✅ `DSH_BIN=/path/to/dsh/lib/bin.js dsh-desktop` |
| dsh ≥0.1.5 Web 认证自动完成 | ✅（自行签发并验证 cookie，见上文；Windows 版同） |
| 系统托盘（X=最小化到托盘） | ⚠️ 无托盘（平台差异：Linux 关闭窗口即退出，服务随启动器停止） |
| 自动安装依赖与 dsh | ✅ 首次启动引导（见上文） |
| 图标/标题镜像/窗口内导航/端口跟随/日志 | ✅ 全部一致 |

> 差异说明：Linux 无系统托盘，主窗口关闭 = 退出程序（与 Windows「X=最小化到托盘」不同，
> 服务仍由启动器正确停止）；分离出的子窗口关闭只关自身。

## 目录结构

```
dsh-desktop.py      WebKitGTK 窗口程序
dsh-desktop         bash 启动器（依赖引导/服务检测/启动/认证/清理）
install.sh          免 root 安装脚本
uninstall.sh        卸载脚本（安装时生成）
dsh-desktop.png     应用图标
```

日志：`~/.local/state/dsh-desktop/logs/{server.out.log,server.err.log}`

## 已知问题

- 窗口使用**内存态** WebContext（不落盘、不访问系统密钥环），因此 cookie 只在本进程内有效：
  每次启动都会重新认证（启动器自动完成）。这样也避免了 Deepin 的「解锁登录密钥环」弹窗。
- 交互类操作（关窗停服务/单实例/拖拽分离等）请在真实桌面环境验证。
