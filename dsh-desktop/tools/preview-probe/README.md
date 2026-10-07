# 预览增强：验证工具（开发用）

右侧栏预览的「滚轮缩放 / 拖动平移 / 加粗滑动条」是注入脚本实现的，生效的那份**内嵌在 `../../App.cs`
的 `PreviewToolsScript()`** 里；本目录的 `preview-tools.js` 是同一份脚本的镜像，方便单独跑测试与维护。
同步用 `embed.mjs`（不要手工复制），它同时会校验两份是否一致。

## 生效范围（v1.2.6 起）

脚本只认**右侧栏的文档预览视口**：`[data-sidebar-right-panel]` 内的 `[data-textpreview-body]`，
且右栏面板必须真的可见（收起时 dsh 会给面板 `aria-hidden` + `visibility:hidden` 并把整列移出窗口右侧）。
判定失败就 `unbind()`：删掉 `dsh-pv-vp` 类、摘掉 wheel/mousedown/dblclick 监听、清掉 frame 上的 zoom，
产品原生 8px 滑动条与滚动行为随即恢复。`scan()` 每 500ms 一次，展开/收起/切换预览都会在下一次校验时生效。

> 这条规则是为了修掉一个真实缺陷：旧版对任意「大图 / `<pre>`」向上找可滚动祖先，于是**对话区里的代码块**
> 会让它把整个对话滚动容器接管（14px 滑动条 + 滚轮缩放出现在对话区）。

## 脚本

| 文件 | 用途 |
| --- | --- |
| `preview-tools.js` | 注入脚本镜像（真身在 `../../App.cs`） |
| `embed.mjs` | 镜像 ⇄ App.cs 内嵌副本同步/校验：`node embed.mjs`（检查）/ `--write`（写入）/ `--expect <文件>`（与指定文件对比） |
| `drive.mjs` | 无头 Edge + CDP：自己登录 3080、打开右栏文件预览、用**真实鼠标事件**测缩放/平移，可 `--apply` 注入脚本 |
| `attach.mjs` | 附着到**正在运行的桌面窗口**（先用 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9340` 启动）做同样的实测 |
| `eval.mjs` | 通用「登录后执行任意 JS」探针 |
| `check-text.js` | 文本/代码预览的行为核查（普通滚轮仍滚动、Ctrl+滚轮缩放、拖动不平移） |

## 用法

```powershell
# 0) 改完 preview-tools.js 后同步进 App.cs（会自动校验）
node embed.mjs --write; node embed.mjs

# 1) 无头验证（不改动任何窗口）
node drive.mjs --steps "dsh-desktop,docs,banner.png" --apply preview-tools.js --shot .\shots\a

# 2) 真实窗口验证
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9340'
& "$env:LOCALAPPDATA\Programs\DSH Desktop\dsh-desktop\DSH Desktop.exe" http://127.0.0.1:3080
node attach.mjs --port 9340 --steps "dsh-desktop,docs,banner.png"
```

脚本会自动用 `~/.dsh/.credentials.yaml` 里的签名密钥签一枚 3080 的会话 cookie（与启动器同一算法），
所以**不需要**手工登录，也不需要 token。