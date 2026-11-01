# DeepSeek Harness 管理器（Windows 版）

Windows 发行版：**管理器 + 会话窗口是同一个程序**（WPF + WebView2），
不再有独立的 `DSH Desktop.exe` / `launcher.ps1` 那两个东西。

## 安装

```powershell
powershell -ExecutionPolicy Bypass -File install-win.ps1
```

装到 `%LOCALAPPDATA%\Programs\DSH Manager`，并在桌面与开始菜单建快捷方式（免管理员）。

## 卸载

```powershell
powershell -ExecutionPolicy Bypass -File uninstall-win.ps1        # 保留数据
powershell -ExecutionPolicy Bypass -File uninstall-win.ps1 -Purge # 连配置一起删
```

## 它做什么

- 扫描本机 DSH 安装：npx 缓存 / pi-node / 全局 npm / `%DSH_HOME%\profiles` /
  PATH / 管理器新建的实例；正在跑的服务按端口反查 PID，显示的是真实端口
- 启动、停止、重启、检查更新、修复、卸载（只动管理器自己创建的实例，
  系统的 npx / pi-node / 全局安装只检查不修改）
- **打开窗口 = 内置会话窗口**：WebView2 装在管理器进程里，**直连实例自己的端口**
  （`127.0.0.1:<port>`，不经过任何代理），自动注入自签的认证 cookie
  （服务是外部启动的也能直接进），同一个端口只开一个窗口；服务没在跑会先拉起来
- **手机端桥（只给手机/平板用）**：`dsh-mobile-bridge` 监听局域网 8099、反代到本机实例，
  手机上打开 `http://<本机IP>:8099/` 就能用；管理器启动服务时会为每个局域网 IP
  补 `--trusted-host <ip>:8099`，否则桥转过来的 `/api` 会被 DSH 的来源栅栏拦掉。
  电脑端窗口**不走桥**（同一台机器上绕一圈没意义，还多一个「桥没在跑」的依赖）
- **窗口跟着主题走**：管理器的昼/夜会同步给页面（`prefers-color-scheme`），
  窗口里外一个色，不会出现「管理器黑、网页白」
- 插件管理：GitHub `topic: dsh-plugin` 发现，安装 / 更新 / 卸载
- 主题：7 套 × 昼/夜（14 个配色），和 Linux 版同一套 tokens
- 图标：沿用旧启动器的黑色鲸鱼（程序图标 / 快捷方式 / 任务栏 / 侧栏品牌位）
- 单实例 + 托盘：点 X 收进托盘，真正退出在托盘菜单；再启动一次只是把窗口提到前台
- 窗口可以缩到 1/4 屏（720×450），布局自动响应式收窄

## 命令行（自检/脚本用）

```
DshManager.exe                                 正常启动
DshManager.exe --open [--open-hold 30]         直接开内置会话窗口（N 秒后退出）
DshManager.exe --shot out.png --theme frost --mode night --size 720x450
DshManager.exe --plugins --shot p.png          插件对话框截图
DshManager.exe --newinstance --shot n.png      新建实例对话框截图
DshManager.exe --selftest-actions              对每个实例跑一遍修复自检
DshManager.exe --selftest-install <dir>         真装一份实例，再跑 修复/更新/卸载
```

日志：`%LOCALAPPDATA%\dsh-manager\`（`crash.log`、`web.log`、`logs\<实例>.log`）。

## 文件位置

| 内容 | 路径 |
| --- | --- |
| 设置（日志行数） | `%APPDATA%\dsh-manager\settings.json` |
| 主题 | `%APPDATA%\dsh-manager\win-settings.json` |
| 实例登记表 | `%APPDATA%\dsh-manager\instances.json` |
| 服务日志 | `%LOCALAPPDATA%\dsh-manager\logs\` |
| WebView2 数据 | `%LOCALAPPDATA%\dsh-manager\webview2\` |
| 插件缓存 | `%LOCALAPPDATA%\dsh-manager\plugins-cache.json` |

用户数据（会话 / profile / 技能）仍然在 `%USERPROFILE%\.dsh`，和管理器无关。

## 依赖

- Windows 10/11
- WebView2 运行时（系统一般已带；缺失时管理器会提示）
- 要管理的 DSH 需要 Node.js（PATH 上）
