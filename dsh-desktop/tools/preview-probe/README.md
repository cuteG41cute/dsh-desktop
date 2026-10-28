# 预览增强：验证工具（开发用）

右侧栏预览的「滚轮缩放 / 拖动平移 / 加粗滑动条」是注入脚本实现的，生效的那份**内嵌在 `../../App.cs`
的 `PreviewToolsScript()`** 里；本目录的 `preview-tools.js` 是同一份脚本的镜像，方便单独跑测试与维护。
同步用 `embed.mjs`（不要手工复制），它同时会校验两份是否一致。

## 生效范围（v1.2.7 起：只认图片 / PDF；PDF 走独立分支，见下）

判定链依次是：

1. `[data-sidebar-right-panel]`（右栏面板）**必须可见**——收起时 dsh 会给面板 `aria-hidden` + `visibility:hidden`
   并把整列移出窗口右侧（grid 列归零）；
2. `[data-document-preview]`（预览渲染器）里的 `[data-textpreview-body]`（预览滚动体）；
3. **PDF 优先**：里面有 `[data-pdf-page]`（`…/documentpreview/pdf` 渲染器）→ 直接走 PDF 分支；
4. 否则要求里面**没有**文本类标记（`pre` / `[data-textpreview-plain]` / `[data-textpreview-page]` / `[data-code-preview]`）；
5. 能找到真正的媒体元素（`img` / `canvas` / `embed` / `object` / `iframe` / `video`）。

命中 1+2+3（或 1+2+4+5）才绑定；否则 `unbind()`：删掉 `dsh-pv-vp` 类、摘掉 wheel/mousedown/dblclick 监听、
清掉 frame 上的 zoom 与 PDF 的内联宽度 / `overflow` 覆盖，产品原生 8px 滑动条与滚动行为随即恢复。`scan()` 每 500ms 一次。

### PDF 与图片是两套缩放（2026-10-16）

| 内容 | 缩放方式 | 滚轮 | 双击 |
| --- | --- | --- | --- |
| 图片 `[data-image-preview] > img` | frame 上写 CSS `zoom`（按实测位移校正锚点） | 直接缩放 | 适宽 ↔ 1:1 |
| PDF `[data-pdf-page] > canvas`（一页一个） | **按页写绝对像素宽度**（`--pdf-page-width` × 倍率），并临时把页 / 正文容器的 `overflow` 改成 `visible` | **Ctrl + 滚轮**才缩放，单滚轮保持上下滑动 | 适宽 ↔ 100% |

为什么 PDF 不能沿用图片那一套：产品把画布宽度写成 `width:min(var(--pdf-page-width),100%)`，
而 frame 只是**第一页**的容器、两层容器还带 `overflow-x:hidden` —— CSS `zoom` 会把百分比宽度一起缩掉
（徽标显示 800% 而画面缩回一屏）、只影响第一页、溢出的部分被裁掉滚不到。
写绝对像素宽度之后：缩放是**全局的**（所有页一起）、可以放大到超出显示区域并横向滚动、100% 就是真正的 1:1。
后几页是**滚动到位才渲染**的（渲染时才写 `--pdf-page-width`），渲染完成的那一刻由 `pdfKeepUp()` 按同一倍率补齐；
用户还没缩放过时一律不写内联宽度，保持产品自己的响应式排版。

实测（`verify-pdf-zoom.mjs`，真实窗口 + 真实滚轮）：

| 检查 | 旧版 | 新版 |
| --- | --- | --- |
| 单滚轮 | scrollTop **0 → 0**（被吃掉），第一页被 `zoom` 到 51% 且画布 594 → **403px** | scrollTop **0 → 450**，无内联宽度、无 CSS zoom |
| Ctrl+滚轮×4 | 只有第一页变（其余页不变） | 三页一起，各页同宽 |
| 放大到 800% | 第一页画布反而缩到 **426px**（比适宽还小），横向 `maxX = 0` | 6346px > 视口 634px，`maxX = 5733` 可滚 |
| 双击 | 「100%」实际只有 595px | 真 100% = 793px（= `--pdf-page-width`） |
| Ctrl+滚轮是否触发整个 WebView 缩放 | — | dpr / `visualViewport.scale` 未变 |

### 右键菜单（保存 / 复制 / 显示，2026-10-28：图片 → 所有预览）

**任何**预览（图片 / PDF / 文本 / 代码 / Markdown）右键 → 自绘菜单（`#dsh-pv-menu`，挂在 `body`，颜色走产品的主题 token；
方向键移动、Esc 关闭）：**保存到…**（Ctrl+S）、复制文件路径、在资源管理器中显示；
图片另有「复制图片」与缩放项，PDF 另有缩放项，文本另有「复制 / 全选」。

- **保存**：页面把预览头部 `title` 上的**原文件绝对路径**（产品自己展示的那条）用 **base64** 发给宿主，
  `App.cs` 弹 **Windows 原生的另存为对话框**（`InitialDirectory = 桌面`、文件名预填、类型按扩展名预选；
  图片标题「保存图片」、其它类型「另存为」，过滤器图片给三档、其它只给「当前格式 / 所有文件」），
  确认后 `File.Copy` 原文件 —— 逐字节一致，不是把页面里的内容重新编码。base64 是为了绕开
  Windows 路径里的反斜杠与 JSON 转义的纠缠；回执里的路径 / 错误文本也同样 base64（宿主不需要手写 JSON 转义）。
- **复制图片**（仅图片）：`DataObject` 同时放**图片位图 + 文件**（粘到 Word/聊天窗口是图，粘到资源管理器是文件）；
  SVG / 动图这类 `Image.FromStream` 解不开的只给文件。
- **不抢的原生菜单**：输入框 / 链接 / 表单控件 / `contenteditable` 上的右键保持产品自己的菜单；
  对话区、左侧列表、文件树本身完全不碰。

实测（真实桌面窗口，`DSH_DESKTOP_SAVE_TO`）：

| 检查 | 结果 |
| --- | --- |
| 图片右键菜单 | 6 项、挂在 `body`、完整在窗口内、Esc/方向键可用 |
| 保存到…（图片） | 宿主落盘 `banner.png`，**sha256 与源文件一致**、大小一致、页面提示「已保存：<路径>」 |
| 保存到…（PDF） | 落盘 `three-pages.pdf` 1460 B，sha256 一致；菜单里没有「复制图片」 |
| 保存到…（文本） | 落盘 `README.md`，sha256 一致；菜单保留「复制 / 全选」，「全选」确实选中了全文 |
| 保存到…（小图 225×225，未绑定缩放） | 也能保存，字节一致 |
| Ctrl+S | 不开菜单也能直接落盘，字节一致 |
| 原生对话框（图片） | PrintWindow 截图可见「保存图片」标题 + 地址栏 **用户 › twinblade › 桌面** + 文件名预填 `banner`、类型 `PNG 图片文件`；关闭后页面提示「已取消保存」 |
| 原生对话框（PDF） | 标题「另存为」、地址栏同样 **桌面**、文件名预填 `three-pages` |
| 复制图片 | 剪贴板同时有 `banner.png`（FileDropList）与位图 |
| 复制文件路径 | 剪贴板文本 = 绝对路径 |
| 控制台 | 零未捕获异常 |

## 脚本

| 文件 | 用途 |
| --- | --- |
| `preview-tools.js` | 注入脚本镜像（真身在 `../../App.cs`） |
| `embed.mjs` | 镜像 ⇄ App.cs 内嵌副本同步/校验：`node embed.mjs`（检查）/ `--write`（写入）/ `--expect <文件>`（与指定文件对比） |
| `verify-scope.mjs` | **作用范围验证器**：document-start 注入 + 真实滚轮/拖动，逐项核对「对话区/文本/日志=原生，图片/PDF=增强，收起右栏=全部失效」 |
| `verify-pdf-zoom.mjs` | **PDF 缩放验证器**：真实页面/真实窗口里的 PDF 三件事（全局、可超出显示区域、Ctrl+滚轮），`--edge`（无头，自己登录并注入）/ `--attach <端口>`（附着到真实窗口）/ `--observe`（只记录不断言，用来对比旧版） |
| `verify-preview-menu.mjs` | **预览右键菜单验证器**：无头真实页面上注入脚本 + 假宿主桥，用真实右键事件核对「图片 / 小图 / PDF / 文本」四类预览的菜单项、发出的保存消息（路径 / 文件名）、回执提示，以及文本的「复制 / 全选」 |
| `fixtures/three-pages.pdf` | 验证用 3 页 A4 夹具（由 `.tmp` 里的 make-pdf 生成，已入库，可直接用） |
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

# 1) PDF 缩放：无头（真实产品页面，自己注入脚本）
node verify-pdf-zoom.mjs --edge --inject preview-tools.js
# 1b) PDF 缩放：附着到真实桌面窗口（exe 已经把脚本注入进去了）
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9340'
& "$env:LOCALAPPDATA\Programs\DSH Desktop\dsh-desktop\DSH Desktop.exe" http://127.0.0.1:3080
node verify-pdf-zoom.mjs --attach 9340
# 1c) 换成旧 exe（安装目录里的 DSH Desktop.exe.old-*）再看一遍，就是 before/after
node verify-pdf-zoom.mjs --attach 9341 --observe

# 2) 无头验证（不改动任何窗口）
node drive.mjs --steps "dsh-desktop,docs,banner.png" --apply preview-tools.js --shot .\shots\a

# 3) 真实窗口验证
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9340'
& "$env:LOCALAPPDATA\Programs\DSH Desktop\dsh-desktop\DSH Desktop.exe" http://127.0.0.1:3080
node attach.mjs --port 9340 --steps "dsh-desktop,docs,banner.png"
```

脚本会自动用 `~/.dsh/.credentials.yaml` 里的签名密钥签一枚 3080 的会话 cookie（与启动器同一算法），
所以**不需要**手工登录，也不需要 token。