# dsh-manager 3.0.1

修一个**新建源码实例会失败**的问题。Windows 安装包；Linux 同版本号一并发布（无功能变化）。

## 问题：`pnpm install 失败：退出码 1: [ERR_PNPM_NO_PKG_MANIFEST]`

现象：新建实例（安装方式 = 官方仓库源码）在克隆仓库之后立刻失败，日志里只有一句
`ERR_PNPM_NO_PKG_MANIFEST`。

根因：上一次克隆被中断（网络抖动 / 提前关窗口），在实例目录里留下了一个**不完整**的
`app/.git`（只有 `objects/`，没有 `HEAD`），工作区里也没有 `package.json`。
旧代码判断「`app/.git` 存在 ⇒ 仓库已克隆好」，于是**跳过 clone**，直接在一个空目录里跑
`pnpm install` —— pnpm 找不到 `package.json`，就是这个报错。重试也一样，因为坏目录一直在。

## 修复

1. 「能不能跳过克隆」改成**校验检出是否可用**：要求 `app/.git/HEAD` 存在 **且**
   `app/package.json` 存在；不满足就打印
   「检测到上次没克隆完整（缺 package.json 或 .git 不完整），清理后重新克隆」，
   删掉坏目录再重新 clone；
2. clone 完成后同样做一次校验，不完整就给出明确提示（「克隆结果不完整（工作区里没有 package.json），
   多半是网络中断导致」），而不是继续跑到 pnpm 才崩；
3. 新增 `--selftest-source <目录>` 命令行自检：直接走「源码检出」安装流程
   （与新建实例同一条代码），日志写进 `%LOCALAPPDATA%\dsh-manager\source-test.log`，
   方便以后在没有界面的情况下排查 clone/pnpm 链路。

## 验证

用一份**故意造出来的坏检出**（只有 `app/.git/objects` + `node/`）跑 `--selftest-source`：

```
[source-test] dir=... ref=master
实例里已经有 Node，跳过下载
便携 Node 就绪
检测到上次没克隆完整（缺 package.json 或 .git 不完整），清理后重新克隆
克隆官方仓库：https://github.com/deepseek-ai/deepseek-harness.git
使用仓库版本：master
Cloning into '...app'...
```

随后 clone 成功（工作区出现 `package.json`、`apps/`、`packages/` …），
`pnpm install` 正常开始下载依赖（Progress: resolved 1434, added 770+）。

## 你现在要做的

1. 管理器已装 **3.0.1**（也可以从本 Release 重新下载 `DshManager.exe`）；
2. 直接**再点一次「创建实例」**即可：上次那个坏目录会被自动清理并重新 clone；
3. 源码安装本身要 10–20 分钟（clone → pnpm install → pnpm run build），中途别关窗口；
   已经下好的 Node / pnpm-store 都会被复用，重试不会从零开始。

Linux 版 3.0.1 与 3.0.0 功能相同，只是保持两端版本号一致。
