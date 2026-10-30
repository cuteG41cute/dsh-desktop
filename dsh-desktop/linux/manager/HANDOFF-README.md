# dsh-manager UI 复刻包（设计稿 + 当前实现 + 任务说明）

给虚拟机上的 DSH agent 用。**先读 `PROMPT.md`**——那是完整任务书
（目标 / 环境 / 文件位置 / 工作流 / GTK3 硬限制 / 40 项功能测试矩阵 / 交付物）。

## 一分钟看懂包里有什么

| 目录 | 是什么 |
| --- | --- |
| `PROMPT.md` | **任务书**（要通读） |
| `design/` | Kimi 的设计稿原件：`index.html` / `styles.css`（唯一色值来源）/ `app.js` / `references/`（7 主题 × 日/夜 参考图） |
| `project/dsh-desktop/linux/` | 当前实现：桌面壳 + 管理器（`manager/dsh_manager/gui.py` 是主要战场） |
| `project/.../dsh_manager/theme/`、`backgrounds/` | **生成物**，不要手改（见 PROMPT §4） |
| `project/.../tools/` | 主题生成器 + 全部 gate |
| `tools/vm-verify.sh` | 一键：全部 gate + 构建 deb + 打印 sha256 |

## 三条最快的命令

```bash
cd ~/share/dsh-manager-ui-redesign
sudo apt update && sudo apt install -y spectacle imagemagick python3-pil
bash tools/vm-verify.sh            # 基线（应全绿）
```

## 关键上下文（避免重复踩坑）

1. **主题 CSS 是全有或全无**：一个非法值就整份丢弃 → 界面裸奔。曾因
   `@define-color dsh_accent_rgb 121,104,232;` 踩过，`theme-token-check.py` 现在会拦。
2. **GTK3 没有** `backdrop-filter` / `transform` / CSS 变量 / flex；`GtkLabel` 也不画背景
   （色块要用 `Gtk.EventBox`，代码里已有 `_chip()`）。细节见 PROMPT §6，别去追做不到的。
3. **改样式 = 改模板再生成**：`tools/gtk-theme-template.css.in` → `build-gtk-theme.py`
   → `dsh_manager/theme/*.css`；直接改生成物会在下次生成时被覆盖且 gate 变红。
4. **装完 deb 必须重开管理器窗口**，否则跑的是内存里的旧代码。
5. 这台机器没装截图工具；Wayland 下 **只有 `spectacle` 截得到窗口**（`import`/`scrot` 不行）。
6. 多实例：控制套接字与单实例锁**按端口**区分（`dsh-desktop-<uid>-<port>.sock`），
   别改回全局唯一，否则第二个实例的窗口开不出来。
7. 原生截屏桥依赖 `xdg-desktop-portal` 的 `Screenshot`（`interactive=false`），
   与插件 `dsh-screenshot` 1.3.1 配套——那是另一件事，本任务**不用动**。

## 现状版本

管理器 `MANAGER_VERSION = 1.3.2`（7 套主题 × 日/夜，令牌由设计稿生成；gate 全绿）。
