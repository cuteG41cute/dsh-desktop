# dsh-manager 3.0.2

这一版修四个问题，都来自「新建源码实例」的那一轮反馈。

## 1. 实例名 → 安装目录：只同步了第一个字母

原因：改名时直接给「安装目录」赋新值，这个赋值又触发目录的 TextChanged，
把「用户手动改过目录」的标记点亮了 —— 于是只有第一次改名会同步，之后就不动了。

改成走 `SetDirSilently()`（程序赋值不点亮标记）。现在：**只要没手动动过目录**，
改实例名会一直跟着同步；手动改过目录（或点过「浏览…」）之后就不再覆盖你的选择。

## 2. 进度条没修好

原来那块灰色条其实是**空日志卡**（没有高度、没有内容，看着像坏掉的进度条）。
现在换成：

- 一条真正的 `ProgressBar`（安装期间一直跑，结束/出错自动隐藏）；
- 下面是有最小高度（96px）的日志区，`git clone / pnpm install / pnpm run build` 的输出实时滚动；
- 安装一开始就把这块显示出来，不再依赖「第一条日志」才露出。

## 3. `ERR_PNPM_NO_PKG_MANIFEST` 仍然出现

这次加了**自恢复**，不再只是「检测坏目录」：

- clone 前：`app/.git/HEAD` + `app/package.json` 齐全才算可用，否则清掉重克隆；
- `pnpm install` 如果报 `NO_PKG_MANIFEST`（或 `app/package.json` 消失），
  **自动清掉 app、重新 clone、再试一次**，并把过程写进日志；
- **同一目录加并发锁**：两次同时点「创建实例」会互相删掉对方的 `app`，
  这正好能造出「在空目录里 pnpm install」的现场 —— 现在第二个请求会直接提示
  「这个目录已经有一次安装在跑」。

## 4. Node / dsh 旧文件不完整

- 实例里的 `node/` 目录存在但 `node.exe` 不在（上次下载/解压中断）→ **清掉重装**；
- 实例里的 `tools/`（pnpm）目录存在但 `pnpm.cjs` 不在 → **清掉重装**；
- 只动实例自己目录下的 `node/`、`tools/`、`app/`，**不碰 `dsh-home/`、用户文件与项目清单**。

## 验证情况（如实说）

- 用一份「只有 `app/.git/objects`、没有 `package.json`」的坏目录跑自检：
  日志出现「检测到上次没克隆完整…清理后重新克隆」→ 重新 clone 成功
  （出现 `package.json`、`apps/`、`packages/`）→ `pnpm install` 正常开始跑；
- 继续观察 `pnpm install`：`resolved 1434 / added 1433`，**卡在最后 1 个包**：
  ```
  [WARN] GET https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz error (ERR_PNPM_FETCH_TIMEOUT)
  ```
  这是 **cdn.sheetjs.com 访问不通**（不是包管理器的问题）。我这次没能等它跑完，
  所以**没有拿到「完整安装成功」的端到端证据** —— 这点必须说清楚。
- 桌面对话框已用离屏渲染截图确认布局正常（空闲时进度条/日志区折叠，安装时展开）。

## 如果重试仍失败

按日志里的关键词对症：

- 再次出现 `NO_PKG_MANIFEST` → 说明自动恢复也没救回来，请把对话框里的日志整段发我；
- 出现 `ERR_PNPM_FETCH_TIMEOUT` / `cdn.sheetjs.com` → 是网络，换网络或挂代理重试即可
  （已下载的 Node / pnpm-store 会复用，不会从零开始）；
- 出现 `git clone 失败` / `克隆结果不完整` → 同上，换网络重试。

Linux 版 3.0.2 与 3.0.1 功能相同，只是保持两端版本号一致。
