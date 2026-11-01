# DeepSeek Harness 管理器（Windows 版）

Windows 发行版：**管理器 + 桌面窗口是同一个程序**（WPF + WebView2），不再有独立的
`DSH Desktop.exe` / `launcher.ps1`。

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

- 扫描本机 DSH 安装：npx 缓存 / pi-node / 全局 npm / `%DSH_HOME%\profiles` / PATH / 管理器创建的
- 启动、停止、检查更新、修复、卸载（只动管理器创建的实例）
- 打开窗口 = 内置 WebView2 会话窗口（自动注入认证 cookie，每端口单实例）
- 插件管理：GitHub `topic: dsh-plugin` 发现，安装/更新/卸载
- 主题：7 套 × 昼/夜，配色与 Linux 版一致
- 单实例 + 托盘：点 X 收进托盘，真正退出在托盘菜单

## 依赖

- Windows 10/11
- WebView2 运行时（系统一般已带；缺失时管理器会提示）
- 要管理的 DSH 需要 Node.js（PATH 上）
