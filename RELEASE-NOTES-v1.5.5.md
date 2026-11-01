# dsh-manager 1.5.5 — Linux 版向 Windows 版对齐

Windows 版（1.0.3）这一轮打磨过的交互，逐项搬到 Linux 管理器上。功能与 1.5.1 一样，改的是
**子窗口行为、图标、实例行信息和主题联动**。

## 这一版改了什么

### ① 子窗口：无边框卡片 + 非模态

- 之前所有对话框都是 `Gtk.Dialog` + `Gtk.HeaderBar` + `modal=True`：
  标题栏里叠一层系统装饰，而且 GTK 的 modal 锁的是**整个应用** —— 开着「管理插件」时，
  管理器点不动，DSH 窗口也一起被锁。
- 现在统一成：无系统标题栏（自绘标题区：大标题 + 副标题 + 右上 ✕）、`set_modal(False)`；
  查看型窗口（插件 / 日志正文 / 密钥）从 `dlg.run()` 换成 `dlg.show()`
  （`run()` 会临时把它模态化）。标题区可拖动窗口。
- 踩坑：Wayland 下 `set_decorated(False)` 会被忽略（GTK 退回服务端装饰，KWin 照样画一条
  标题栏）；解法与主窗口一致 —— `decorated=True` + 零高度占位标题栏 → 协商成 CSD。

### ② 图标：沿用旧启动器的黑色鲸鱼

- 侧栏品牌位从紫色渐变「D」方块换成**白底圆角 + 黑色鲸鱼**（`icons/whale.png`，
  与 Windows 版、程序图标同一张图）；
- 窗口/任务栏图标本来就是同一只鲸鱼（`share/dsh-desktop.png`），这一版保证它一定随包安装
  （`build-deb.sh` 之前只拷 `icons/*.svg`，PNG 会漏）。

### ③ 插件对话框

- 单层标题区（不再有系统标题栏 + 卡片标题两层）；
- 状态列按主题上色：已安装 = 绿、半装 = 红、其余 = 灰；
- 底部操作条与 Windows 一致（安装/更新 · 卸载 · 导入本地包 · 刷新状态 · 打开仓库 · 刷新 GitHub 列表 · 关闭）。

### ④ 实例行信息

- 第二行从 `v0.21.5-rc.5` 改成 `dsh 0.21.5-rc.5 · PID 177327`（定时刷新同步），
  和 Windows 版一样把版本与进程一眼看全；端口在详情卡里。

### ⑤ 窗口直连 + 主题联动

- 复核「打开窗口」：管理器给实例的环境是 `DSH_WEB_URL=http://127.0.0.1:<port>`，
  实测窗口进程 cmdline 是 `dsh-desktop.py http://127.0.0.1:3081` —— **不经过手机端桥**；
- **管理器的昼/夜同步给页面**（新增）：管理器切主题时把 `DSH_DESKTOP_MODE=day|night`
  写进环境，窗口进程据此只给自己设 `gtk-application-prefer-dark-theme`（不动系统设置），
  WebKitGTK 的 `prefers-color-scheme` 随之变化。

## 验证（VM 上真跑，非推断）

| 检查 | 结果 |
| --- | --- |
| 插件对话框 | `modal=False decorated=False`；管理器 `sensitive=True`；截图里无系统标题栏 |
| 侧栏品牌 | 安装版 1.5.5 启动即鲸鱼白块；任务栏图标同一只 |
| 实例行 | 程序内读控件：`dsh 0.2.1-rc.5 · 端口 3081 · PID 177327` |
| 窗口直连 | `dsh-desktop.py http://127.0.0.1:3081`（无 8099） |
| 主题联动 | 管理器导出 `DSH_DESKTOP_MODE=night/day` → 页面区域平均亮度 **82.3 / 255.0** |

## 安装 / 升级

```bash
sudo dpkg -i dsh-manager_1.5.5_all.deb
```

装完从应用菜单重开「DeepSeek Harness 管理器」即可（正在开着的旧窗口要关掉重开）。

## 已知差异（没跟 Windows 完全一致的地方）

- Windows 版对话框的柔和投影在 Wayland 下拿不到（KWin 不给无边框窗口加阴影），
  Linux 这边只有圆角，没有外发光；
- Windows 版侧栏有「来源徽标」（NPX / DSH），Linux 的实例都是本地前缀，
  用首字母徽标（D1 / D2）表示身份，没有做来源区分。
