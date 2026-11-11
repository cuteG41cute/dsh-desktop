# 双端同步规则（Windows / Linux 管理器）

从 **3.0.0** 起，Windows 与 Linux 管理器使用**同一个版本号**，并且在同一个 Release 里一起发布。

## 1. 版本与发布

| 项目 | 规则 |
| --- | --- |
| 版本号 | 两端**必须相同**（3.0.0、3.0.1 …），不再出现 `win-v2.0.34` 与 `v1.5.7` 这种各走各的情况 |
| Tag | 统一用 `v<版本>`（例如 `v3.0.0`），一个 tag 一个 Release |
| 资产 | 同一个 Release 同时上传：`DshManager.exe`（Windows）、`dsh-manager_<版本>_all.deb`（Linux）、两端各自的说明与 README |
| 构建 | Windows 用 `dsh-manager-win/build-win.ps1`；Linux 的 deb 用 WSL（`deepin`）跑 `dsh-desktop/linux/manager/build-deb.sh` |
| 版本号写入点 | Windows：`dsh-manager-win/DshManager.csproj` 的 `<Version>/<FileVersion>/<AssemblyVersion>`；Linux：`dsh-desktop/linux/manager/dsh_manager/core.py` 的 `MANAGER_VERSION` 与 `build-deb.sh` 的 `VERSION` |

`tools/bump-version.ps1 -Version 3.0.1` 会一次性改好上述所有位置（不改 WebView2 包版本）。

## 2. 变更同步规则

**Windows 端每做一个改动（新增功能 / 修复 / 回滚 / 改版），Linux 端必须在同一轮里跟上：**

1. 改 Windows 代码；
2. 找 Linux 对应实现：`dsh-desktop/linux/manager/dsh_manager/{core.py,gui.py,plugins.py}`（管理器）或
   `dsh-desktop/linux/dsh-desktop.py`（会话窗口 / 注入脚本）；
3. 注入类脚本（`dsh-manager-win/web/*.js`）**两端共用同一份文件**：Linux 侧从同一路径读取注入，
   不要复制副本，避免再出现「改一边忘一边」；
4. 两端都构建、都自测（Windows 本机 + Linux 至少做语法/CLI 冒烟）；
5. **同一个版本号、同一个 Release** 一起推送。

回滚同理：Windows 回滚某个功能时，Linux 同一功能也要回滚，不能留一半。

## 3. 功能矩阵（3.0.0 目标）

| 能力 | Windows 2.0.34 | Linux 1.5.7 | 3.0.0 目标 |
| --- | --- | --- | --- |
| 多实例管理（新建/启停/窗口/更新/修复/卸载） | ✅ | ✅ | 对齐 |
| 新建实例：源码检出（clone + pnpm + build） | ✅ | ❌（npm 安装） | 见 §4 决策 |
| 新建实例：目录自动避让 | ✅ | ✅（`deepseek-harness-N`） | 对齐 |
| 新建实例：非空目录校验（允许复用 node/tools/pnpm-store/app） | ✅ | ✅（3.0.0 已补） | 对齐 |
| 新建实例：端口占用校验 | ✅ | ✅（3.0.0 已补） | 对齐 |
| 新建实例：便携 Node 下载重试 + 进度 | ✅ | ✅（Linux 一直有 pulse） | 对齐 |
| 安装失败清理半成品目录 | ✅ | 待补 | 补 |
| 启动就绪等待 | 60s | 90s | 对齐（Linux 更宽） |
| 删除/卸载：等端口释放 + 清只读 + 重试 | ✅ | ✅（3.0.0 已补） | 对齐 |
| 日志卡片只在安装时显示 | ✅ | 待确认 | 补 |
| UI 看门狗（hang.log） | ✅ | 待补 | 补 |
| 会话窗口：预览右键（保存/复制路径/资源管理器/复制图片） | ✅ | 待移植 | 移植 |
| 会话窗口：输入框右键（剪切/复制/粘贴/全选） | ✅ | 待移植 | 移植 |
| 会话窗口：文件夹拖入（`__DSH_HOST_PATHS__` 桥） | ✅ | 待移植 | 移植 |
| 会话窗口：文件/目录/交付卡拖出 | ✅ | 部分（旧 preview-tools） | 移植 |
| 会话窗口：图片放大后拖动平移 | ✅ | 待移植 | 移植 |
| 主题/字体/对话框形态对齐 Windows | — | ✅（1.5.x 系列） | 保持 |

## 4. 待决策：Linux 是否也改用源码检出

Windows 从 2.0.0 起是「git clone 官方仓库 + 实例内 pnpm install/build」，Linux 仍是「npm 装 `@deepseek-ai/dsh`」。

- 好处（源码检出）：版本可选到 tag、能跑仓库里的最新代码、与 Windows 一致；
- 代价：Linux 侧要多实现 clone/pnpm/build/失败清理/断点复用，且本机没有 Linux 图形环境做端到端验证（只有 WSL 可跑 CLI）。

**当前建议**：3.0.0 先不强行统一安装方式（两种都能满足「独立实例 + 可选版本 + 独立 dsh-home」），
把两边**行为**对齐（校验、清理、删除、窗口增强），等有 Linux 图形测试环境再切源码检出。

## 5. 发布检查单

- [ ] 两端版本号一致（`bump-version.ps1`）
- [ ] 两端都能构建（exe / deb）
- [ ] 至少冒烟：Windows 启动 + 建实例对话框；Linux `--headless` 或 `dpkg -i` 解包校验
- [ ] 同一个 tag：`v<版本>`
- [ ] Release 同时含 exe + deb + 两端说明
- [ ] 发布后 `git ls-remote` 与 Release 资产哈希核对


## 6. 状态（2026-11-11）

**v3.0.0 已发布**（同一个 Release：`DshManager.exe` + `dsh-manager_3.0.0_all.deb` + 双端说明）。

已完成并验证（Linux 侧在真实 Ubuntu 26.04 + GTK 3.24 + WebKitGTK 4.1 虚拟机里逐项确认）：

- 侧栏「＋」→ 刷新按钮（转圈 + toast）
- 仪表盘底部「删除实例」卡（软红按钮，确认后卸载）
- 新建实例：端口占用 / 非空目录校验
- 安装失败清理半成品目录（只删本次新建的）
- 卸载健壮化（等端口释放 + 清权限重试）
- 最近日志 15 条
- UI 看门狗 hang.log
- 顶栏「窗口功能」+ 两个开关（写入 settings.json 并实际控制注入）
- 会话窗口 5 项增强（与 Windows 共用同一份 JS；控制套接字断言 `__dshPan / __dshMenu / __dshTextMenu / __dshDragOutLinux / __DSH_HOST_PATHS__` 全部为真，且合成右键事件在预览区/输入框/正文三处的行为符合预期）

后续每次改动都要按第 2 节的规则双端同步。
