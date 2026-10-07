# 预览增强：验证工具（开发用）

右侧栏预览的「滚轮缩放 / 拖动平移 / 加粗滑动条」是注入脚本实现的，生效的那份**内嵌在 `../../App.cs`
的 `PreviewToolsScript()`** 里；本目录的 `preview-tools.js` 是同一份脚本的镜像，方便单独跑测试与维护。
同步用 `embed.mjs`（不要手工复制），它同时会校验两份是否一致。

## 生效范围（v1.2.7 起：只认图片 / PDF）

判定链依次是：

1. `[data-sidebar-right-panel]`（右栏面板）**必须可见**——收起时 dsh 会给面板 `aria-hidden` + `visibility:hidden`
   并把整列移出窗口右侧（grid 列归零）；
2. `[data-document-preview]`（预览渲染器）里的 `[data-textpreview-body]`（预览滚动体）；
3. 里面**没有**文本类标记（`pre` / `[data-textpreview-plain]` / `[data-textpreview-page]` / `[data-code-preview]`）；
4. 能找到真正的媒体元素（`img` / `canvas` / `embed` / `object` / `iframe` / `video`）。

命中 1+2+3+4 才绑定；否则 `unbind()`：删掉 `dsh-pv-vp` 类、摘掉 wheel/mousedown/dblclick 监听、
清掉 frame 上的 zoom，产品原生 8px 滑动条与滚动行为随即恢复。`scan()` 每 500ms 一次。

实测（`verify-scope.mjs`，真实鼠标/滚轮）：图片与 PDF 命中（14px 滑动条、滚轮缩放、拖动平移 1:1 跟手）；
文本 `.ps1`、`.log`、工作区文件列表、对话区一律不命中（8px 原生滑动条、滚轮就是原生滚动）。
dsh 的 PDF 预览用的是图片渲染器（`…/documentpreview/image`），所以 PDF 天然落在增强那一档。

> 规则是为了修掉两个真实缺陷：① 旧版对任意「大图 / `<pre>`」向上找可滚动祖先，
> 于是**对话区里的代码块**会让它接管整个对话滚动容器；② 文本/日志预览被加粗滑动条与缩放接管，
> 和产品自己的操作逻辑打架。

> 缩放与平移都按 **frame 的实测位移**校正（`moveContent()`）：CSS `zoom` 会改变滚动坐标与实际位移的比例，
> 直接加减 `scrollTop` 会出现「拖 100px 却动 200px」甚至方向相反的手感。

## 脚本

| 文件 | 用途 |
| --- | --- |
| `preview-tools.js` | 注入脚本镜像（真身在 `../../App.cs`） |
| `embed.mjs` | 镜像 ⇄ App.cs 内嵌副本同步/校验：`node embed.mjs`（检查）/ `--write`（写入）/ `--expect <文件>`（与指定文件对比） |
| `verify-scope.mjs` | **作用范围验证器**：document-start 注入 + 真实滚轮/拖动，逐项核对「对话区/文本/日志=原生，图片/PDF=增强，收起右栏=全部失效」 |
| `drive.mjs` | 无头 Edge + CDP：自己登录 3080、打开右栏文件预览、用**真实鼠标事件**测缩放/平移，可 `--apply` 注入脚本 |
| `attach.mjs` | 附着到**正在运行的桌面窗口**（先用 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9340` 启动）做同样的实测 |
| `eval.mjs` | 通用「登录后执行任意 JS」探针 |
| `check-text.js` | 文本/代码预览的行为核查（普通滚轮仍滚动、不加类、拖动不平移） |

## 用法

```powershell
# 0) 作用范围验证（最有用；会自动登录并选中工作区，用真实输入事件核对）
node verify-scope.mjs --port 9350 --shot .\shots\scope
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