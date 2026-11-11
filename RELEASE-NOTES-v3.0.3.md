# dsh-manager 3.0.3

这一版专门解决「新建源码实例时的网络问题」：**有代理就走代理**，并且把 clone 失败的自愈做扎实。

## 1. 优先走系统代理

新增代理探测，按这个顺序：

1. 环境变量 `HTTPS_PROXY / HTTP_PROXY / ALL_PROXY`；
2. Windows「Internet 选项」里的代理（注册表 `ProxyEnable` + `ProxyServer`，比如 `127.0.0.1:7890`）；
3. 都没有 → 直连。

两个细节：

- **连不上就回退直连**：系统里常常残留一个早已关掉的代理（上次留下的 `127.0.0.1:7890`），
  如果硬走它，所有网络操作都会失败 —— 所以探测到代理后会先做一次 TCP 连通性检查（600ms），
  不通就直连，并在日志里写明「检测到代理但连不上，已回退直连」；
- **日志里会写明策略**：安装日志第一行就是「网络策略：使用代理 http://127.0.0.1:7890」。

代理会应用到：

- `git clone`（子进程环境变量）；
- `npm install pnpm`（`--proxy` / `--https-proxy`）；
- `pnpm install`（`--config.proxy` / `--config.https-proxy`；只给环境变量 pnpm 实测仍会直连）；
- 管理器自身的 HttpClient（下载 Node、查版本列表、GitHub API）。

## 2. `git clone` 失败的自愈

- 强制 `http.version=HTTP/1.1`（**代理下 `fatal: expected 'packfile'` 的经典修法**）；
- 失败自动重试 3 次，每次清干净再试（含切默认分支）；
- 克隆完再校验「`.git/HEAD` + `package.json` 都在」，不完整按失败处理；
- 删除旧目录前先清只读、重试 3 次，**还被进程占用就改名挪开** ——
  修 `fatal: destination path ... already exists and is not empty`。

## 3. 依赖下载

- `--fetch-retries=5`、`--fetch-timeout=120000`，给慢速/不稳的网络留足重试；
- `pnpm run build` **不再**携带网络参数（之前会把 `--config.proxy` 转发给仓库自己的
  `tsx scripts/build.ts`，导致参数解析失败）。

## 实测情况（如实）

- 代理探测：日志出现 `网络策略：使用代理 http://127.0.0.1:7890`；
- 直连 `cdn.sheetjs.com` → 15 秒超时；走代理 → **HTTP 200 / 0.7 秒**；
- 一次完整跑通到 `pnpm install` **结束**（`node-pty postinstall`、`esbuild postinstall: Done`，
  也就是 `xlsx` 这个以前必然超时的包下载成功了），随后进入 `pnpm run build`；
- 但 `pnpm run build` 那次失败是我加错参数（已修），**修完后没有再次完整跑到 build 结束**；
- 另一轮里 `git clone` 通过代理连续失败 3 次（退出码 128）—— **代理本身不稳**，
  这种情况下重试几次或换节点即可。

## 你重试时看日志的关键词

| 日志 | 含义 | 处理 |
| --- | --- | --- |
| `网络策略：使用代理 …` | 已识别代理 | 正常 |
| `检测到代理 … 但连不上，已回退直连` | 代理没开/端口变了 | 打开代理软件，或忽略 |
| `clone 失败（…），第 N 次重试` | 代理抖动 | 会自动重试；失败就再点一次创建 |
| `ERR_PNPM_FETCH_TIMEOUT` / `cdn.sheetjs.com` | 该域名没走代理 | 在代理规则里放行 `cdn.sheetjs.com` |
| `构建失败：退出码 1` | build 阶段 | 把日志发我 |

Linux 版 3.0.3 与管理器 3.0.2 功能相同（代理逻辑是 Windows 侧），只是保持两端版本号一致。
