# 介绍页（静态站点）

`index.html` 是一份**单文件**介绍页（内联 CSS / 极少量 JS），`assets/` 里是本页用到的真实截图与录屏。
没有任何外部依赖（不引 CDN、不需求字体），断网也能正常打开。

## 怎么看

直接双击 `index.html`，或在仓库根目录起一个静态服务：

```bash
python -m http.server 8080 --directory dsh-desktop/site
# 然后浏览器打开 http://127.0.0.1:8080/
```

想发布到 GitHub Pages 时，把这个目录内容放到你选定的发布目录即可（相对路径都是 `assets/…`，整目录搬走不会坏）。

## 素材是怎么来的

| 文件 | 来源 |
| --- | --- |
| `assets/demo-preview.mp4` | **真实界面录屏**：headless Edge 通过 CDP 抓帧（55 fps / 1280×800），ffmpeg 编码 H.264（19.8 秒 / 约 970 KB） |
| `assets/shot-hero.png` · `shot-files.png` · `shot-zoom.png` · `shot-menu.png` | 同一次录屏里的真实帧 |
| `assets/icon.png` | 应用图标（`linux/dsh-desktop.png`） |

录屏时把桌面宿主才有的**预览增强脚本**（`tools/preview-probe/preview-tools.js`）按宿主的注入方式
（`Page.addScriptToEvaluateOnNewDocument`）提前注入，否则浏览器里看不到缩放与右键菜单。
截图右侧面板的文件路径属于本机用户目录，已在编码时用与面板底色一致的色块**遮挡**（视频与静帧都遮了）。

管理器（GTK）界面无法在 Windows 上截图，页面里那一块是**结构示意图**（SVG），并在图注里写明了这一点。

## 重新录制 / 复检

前置：Windows + Edge（Chromium）、Node ≥ 22（需要全局 `WebSocket`）、ffmpeg（本仓库未附带，
用你自己的一份即可；本机是用 npmmirror 的 `ffmpeg-static` 二进制做的转码）。

```bash
# 1) 录屏：先启动着 dsh web（127.0.0.1:3080），再执行
node dsh-desktop/site/tools/record-demo.mjs --out .tmp/rec/frames --still .tmp/rec/still --session 手机远程对话

# 2) 编码（帧 → mp4）：遮挡框参数见下
ffmpeg -framerate 55 -i .tmp/rec/frames/f%05d.jpg \
  -vf "drawbox=x=548:y=48:w=726:h=19:color=white@1:t=fill" \
  -c:v libx264 -preset slow -crf 24 -pix_fmt yuv420p -movflags +faststart \
  dsh-desktop/site/assets/demo-preview.mp4

# 3) 页面验收：整页截图（桌面 + 移动）、控制台错误、资源 404、横向溢出
node dsh-desktop/site/tools/verify-page.mjs dsh-desktop/site/index.html .tmp/rec/page
```

`record-demo.mjs` 里的 `drawbox` 遮挡坐标是按 1280×800 视口固定的；换分辨率要同步改。

## 页面的内容边界

页面上的数字与结论都来自仓库文档与实测记录（见 `dsh-desktop/README.md` 与「验证」一节），
没有写「未实现」或「没测过」的能力；测不了的部分（OLE 拖放手感、GTK 管理器界面）在页面上
明确标成「需手动确认 / 结构示意」。
