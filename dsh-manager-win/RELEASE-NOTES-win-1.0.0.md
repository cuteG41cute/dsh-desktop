# DeepSeek Harness 管理器 · Windows 版 v1.0.0

Windows 发行版第一次发布：**管理器 + 会话窗口是同一个程序**（WPF + WebView2），
一个工程、一个安装包，不再有独立的 `DSH Desktop.exe` / `launcher.ps1`。

## 下载

- `DshManager.exe`（单文件自包含，63 MB，内置 .NET 运行时，不需要装 .NET）
- `install-win.ps1` / `uninstall-win.ps1`

## 安装

```powershell
powershell -ExecutionPolicy Bypass -File install-win.ps1
```

装到 `%LOCALAPPDATA%\Programs\DSH Manager`，桌面 + 开始菜单建快捷方式（免管理员）。

## 这一版做了什么

- **实例管理**：扫 npx 缓存 / pi-node / 全局 npm / `%DSH_HOME%\profiles` / PATH / 管理器新建的；
  正在跑的服务按端口反查 PID，显示真实端口；启动 / 停止 / 重启 / 检查更新 / 修复 / 卸载
- **内置会话窗口**：WebView2 装在管理器进程里，自动签发并验证认证 cookie
  （服务是外部启动的也能直接进）；同端口单实例；服务没跑会先拉起来
- **手机端**：本机跑着 `dsh-mobile-bridge`（默认 8099）且自检通过时，3080 的实例走桥打开，
  设置里才有「手机端」面板；桥不可用就直连，窗口一定开得出来（`DSH_MANAGER_DIRECT=1` 强制直连）
- **主题联动**：管理器昼/夜同步给页面（`prefers-color-scheme`），不会出现「管理器黑、网页白」
- **插件管理**：GitHub `topic: dsh-plugin` 发现，安装 / 更新 / 卸载
- **新建实例**：用系统 npm 装到独立目录并登记，之后可更新 / 修复 / 卸载（已跑通过完整生命周期）
- **外观**：7 套主题 × 昼/夜（14 个配色，和 Linux 版同一套 tokens）；无边框单边缘、
  Win32 自定义缩放、DWM 圆角、720×450（1/4 屏）响应式布局
- **其它**：单实例 + 托盘（点 X 收进托盘）、帮助 / 关于、日志页、文件管理器定位

## 已知限制

- 会话窗口的最小尺寸是 720×450，和 Linux 版一致
- 「更新」只对管理器自己创建的实例生效；npx / pi-node / 全局安装只检查不修改
