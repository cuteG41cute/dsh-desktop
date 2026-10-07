# 预览增强：验证工具（开发用）

右侧栏预览的「滚轮缩放 / 拖动平移 / 加粗滑动条」是注入脚本实现的，生效的那份**内嵌在 `../../App.cs`
的 `PreviewToolsScript()`** 里；本目录的 `preview-tools.js` 是同一份脚本的镜像，方便单独跑测试与维护
（**改完请同步回 App.cs**，App.cs 才是真身）。

## 脚本

| 文件 | 用途 |
| --- | --- |
| `preview-tools.js` | 注入脚本镜像（镜像 ≠ 真身，见上） |
| `drive.mjs` | 无头 Edge + CDP：自己登录 3080、打开右栏文件预览、用**真实鼠标事件**测缩放/平移，可 `--apply` 注入脚本 |
| `attach.mjs` | 附着到**正在运行的桌面窗口**（先用 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9340` 启动）做同样的实测 |
| `eval.mjs` | 通用「登录后执行任意 JS」探针 |
| `check-text.js` | 文本/代码预览的行为核查（普通滚轮仍滚动、Ctrl+滚轮缩放、拖动不平移） |

## 用法

```powershell
# 1) 无头验证（不改动任何窗口）
node drive.mjs --steps "dsh-mobile-app,assets,icon-foreground.png" --apply preview-tools.js --shot .\shots\a

# 2) 真实窗口验证
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9340'
& "$env:LOCALAPPDATA\Programs\DSH Desktop\dsh-desktop\DSH Desktop.exe" http://127.0.0.1:3080
node attach.mjs --port 9340 --steps "dsh-mobile-app,assets,icon-foreground.png"
```

脚本会自动用 `~/.dsh/.credentials.yaml` 里的签名密钥签一枚 3080 的会话 cookie（与启动器同一算法），
所以**不需要**手工登录，也不需要 token。