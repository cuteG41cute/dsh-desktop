# 发布清单（维护者用）

本目录已经是一个**独立仓库**：代码、测试、安装脚本、CI 都齐了，只差创建远程仓库并推送。
目标仓库名假设为 `cuteG41cute/dsh-file-history`；改名的话，同步改 `package.json` 的
`repository` / `homepage` / `bugs` 和 `README.md` 顶部的 CI 徽章。

## 1. 创建远程仓库并推送（二选一）

### A. 用 GitHub CLI（一条命令建库 + 推送）

```powershell
gh auth login                      # 交互登录；只需一次
gh repo create dsh-file-history --public --source . --push
git push origin v0.4.0             # 见第 2 步先打 tag
```

> 私有仓库把 `--public` 换成 `--private`。安装方需要对应权限。

### B. 网页建库后手动推

在 <https://github.com/new> 创建空仓库 `dsh-file-history`（**不要**勾选自动生成 README/LICENSE），然后：

```powershell
git remote add origin git@github.com:cuteG41cute/dsh-file-history.git
git push -u origin main
git push origin v0.4.0
```

## 2. 打版本标签

```powershell
git tag -a v0.4.0 -m "v0.4.0: per-project switch, status chip shows current footprint"
git push origin v0.4.0
```

## 3. 发布后自检

1. GitHub Actions 的 `test` workflow 变绿（离线自测 + 真依赖契约检查，Node 20/22）。
2. 在**另一台**机器上验证安装：
   ```powershell
   git clone https://github.com/cuteG41cute/dsh-file-history.git
   cd dsh-file-history
   powershell -ExecutionPolicy Bypass -File install.ps1 -Profile web -Force
   # 重启 dsh 服务 / 桌面窗口
   powershell -ExecutionPolicy Bypass -File monitor.ps1
   ```
   期望：`monitor.ps1` 的 8 项判据全部 OK，会话右上角出现「备份」芯片。
3. 让 agent 改一个已存在的文件，确认 `<项目>/.dsh-backup/` 出现带时间戳的备份。

## 3.5 外部改动回传时：先审计，再合并

别人（或另一个 agent）改完传回来的版本**不要直接覆盖**，先跑审计：

```powershell
powershell -ExecutionPolicy Bypass -File audit.ps1 -Path "<回传目录或解压后的目录>"
```

它会做两类检查：

- **30 项机械判据**：必需文件、`package.json` 元数据、`node --check` 语法、`.ps1` 的 UTF-8 BOM、
  本机绝对路径 / 用户名 / npx hash / 密钥泄漏、三处 `inject` 一致性、两套测试、`npm pack` 内容；
- **与基线逐文件差异**：新增 / 删除 / 修改分别列出，供人工过一遍语义变化。

通过（退出码 0）之后再合并回本仓库、提交、打 tag；不通过就带着失败项退回去修。
不做覆盖式合并，避免把回传版本里的构建产物、临时文件或平台专属配置带进发布物。

## 4. 可选：发布到 npm

依赖都在公共 npm 上（`@deepseek-ai/cordis`、`@deepseek-ai/schemastery`），`files` 字段已收敛，
可以直接发：

```powershell
npm login
npm publish --access public
```

之后用户可以直接：

```powershell
dsh plugin --profile web add dsh-file-history
```

（仍需在 `cordis.patch.yml` 登记加载项，或改用 `install.ps1` 让脚本代劳。）

## 5. 备注

- 仓库里**没有**任何本机绝对路径：测试与诊断脚本都会按自身位置 / `$DSH_HOME` / `npx` 缓存动态解析。
- `.ps1` 必须保持 UTF-8 **BOM**（Windows PowerShell 5.1 的 ANSI 回退会把中文语法搞坏）；
  `.gitattributes` 已固定 CRLF，但 BOM 是文件内容，编辑后请用编辑器保存为「UTF-8 with BOM」。
- 版本号从 `0.4.0` 起：`0.x` 阶段不承诺 API 兼容；宿主接口契约见 `HANDOVER.md` 第 3 节。
