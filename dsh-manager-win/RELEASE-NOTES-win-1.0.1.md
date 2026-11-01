# DeepSeek Harness 管理器 · Windows 版 v1.0.1

只改外观，功能与 1.0.0 完全相同。

## 这一版改了什么

- **图标沿用旧启动器的黑色鲸鱼**：
  - 程序图标（`DshManager.exe`）→ 桌面快捷方式、开始菜单、任务栏、Alt+Tab 都是这只鲸鱼；
  - 管理器侧栏品牌位原来是紫色渐变方块里的「D」，现在换成同一只鲸鱼（白底圆角方，深浅主题都认得出）；
  - 会话窗口 / 插件 / 新建实例 / 使用帮助这些窗口的标题栏与任务栏图标也一起换成它。

## 下载

- `DshManager.exe`（单文件自包含，63 MB，内置 .NET 运行时，不需要装 .NET）
- `install-win.ps1` / `uninstall-win.ps1`

## 安装 / 升级

```powershell
powershell -ExecutionPolicy Bypass -File install-win.ps1
```

直接覆盖安装即可（先退出正在运行的管理器，托盘 → 退出）。

## 主要功能（同 1.0.0）

- 实例管理：扫 npx 缓存 / pi-node / 全局 npm / `%DSH_HOME%\profiles` / PATH / 管理器新建的；
  按端口反查在跑的服务；启动 / 停止 / 重启 / 检查更新 / 修复 / 卸载
- 内置会话窗口（WebView2）：自动签发认证 cookie、同端口单实例、服务没跑会先拉起来
- 手机端：本机有 `dsh-mobile-bridge`（8099）且自检通过时，3080 的实例走桥打开
- 主题联动：管理器昼/夜同步成页面的 `prefers-color-scheme`
- 插件管理、新建实例、7 套主题 × 昼/夜、单实例 + 托盘、720×450 响应式布局
