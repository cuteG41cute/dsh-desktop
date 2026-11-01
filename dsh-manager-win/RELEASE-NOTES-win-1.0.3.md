# DeepSeek Harness 管理器 · Windows 版 v1.0.3

只改子窗口的行为，功能与 1.0.2 相同。

## 这一版改了什么

**子窗口改成非模态，不再把整个程序锁住。**

之前「管理插件」「新建实例」「使用帮助」都是 `ShowDialog()`（模态），弹出来之后：

- 管理器窗口被禁用（点不动，只有等它关掉）；
- **DSH 会话窗口也一起被锁** —— 想在插件装的过程中继续跟会话交互，做不到。

现在三个窗口都用 `Show()` 打开：

- 开着「管理插件」时，管理器照常可以点、可以切实例、可以开/关会话窗口；
- DSH 会话窗口完全不受影响，该怎么用怎么用；
- 同一个窗口不会重复开（再点一次是把已开的那个提到前台）；
- 「新建实例」装完仍然会自动刷新实例列表并提示（改成窗口自己的完成事件，不再靠模态返回值）。

`关于` / `卸载确认` 这类「问一句就走」的对话框还是模态的 —— 它们本来就是需要立刻回答的问题。

## 实际验证

用 UIA 在实例化后的程序里点了「打开窗口」+「管理插件」，然后读三个窗口的 `IsWindowEnabled`：

```
== 打开插件窗口之后
  hwnd=0x2F0620 enabled=True  插件 · DeepSeek Harness 管理器
  hwnd=0x210E6E enabled=True  DeepSeek Harness 管理器      ← 没被锁
  hwnd=0x80E88  enabled=True  DeepSeek Harness（会话窗口） ← 没被锁
```

## 下载

- `DshManager.exe`（单文件自包含，63 MB，内置 .NET 运行时，不需要装 .NET）
- `install-win.ps1` / `uninstall-win.ps1`

## 安装 / 升级

```powershell
powershell -ExecutionPolicy Bypass -File install-win.ps1
```

覆盖安装即可（先托盘 → 退出正在运行的管理器）。

## 主要功能

- 实例管理：扫 npx 缓存 / pi-node / 全局 npm / `%DSH_HOME%\profiles` / PATH / 管理器新建的；
  按端口反查在跑的服务；启动 / 停止 / 重启 / 检查更新 / 修复 / 卸载
- 内置会话窗口（WebView2）：直连实例端口，自动签发认证 cookie，同端口单实例，服务没跑会先拉起来
- 子窗口非模态（本版）、主题联动、插件管理、新建实例
- 7 套主题 × 昼/夜、黑色鲸鱼图标、单实例 + 托盘、720×450 响应式布局
