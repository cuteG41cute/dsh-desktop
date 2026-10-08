# dsh-cleaner — 删除会话与工作区

dsh 原生没有删除会话/工作区的入口，本插件在 dsh 进程内补上它。静态常驻插件
（组合加载，重启后随进程一起加载），与 netmon / dsh-time-stamp 同一套结构。

## 功能

| 对象 | 行为 |
| --- | --- |
| **工作区** | 调用产品自己的 `workspaceRegistry.delete(id)`（与官方 workspace 控制器的 `workspace/delete` 同一条产品级路径），只摘登记；工作区下的会话先逐个移入回收目录 |
| **会话** | 先 `detachSession()`（产品原生的登记摘除，走 storage 写链并广播变更 → 侧栏自动刷新），再把会话目录移入回收目录 |
| **孤儿会话** | `sessions/` 下不在任何工作区登记里的目录（多为 `api-*` 接口任务残留），一键移入回收目录 |
| **回收目录** | `~/.dsh/trash/session-cleaner/<时间>_<会话id>/`，带 manifest，面板里可一键恢复（恢复时经 `attachSession` 校验 cwd 后重新登记） |

界面：会话头部新增「**清理**」芯片，点开管理面板——按工作区分组列出全部会话
（标题 / 体积 / 轮次 / 最后活动时间，来自产品的会话投影缓存），删除为**两步确认**；
正在被任何窗口打开的会话一律拒绝删除。

## 安装

1. 把本目录复制到 `<DSH_HOME>/profiles/web/node_modules/dsh-cleaner/`；
2. 在 `<DSH_HOME>/profiles/web/cordis.patch.yml` 追加：

```yaml
    - id: dsh-cleaner
      name: 'dsh-cleaner'
```

3. 重启 harness（组合在启动时加载，刷新页面不够）。

## 边界与说明

- **宿主入口必须 `export default`**：cordis 加载器接受「函数」或「带 apply 方法的对象」作为模块值，
  只有命名导出会被当成裸命名空间对象 → `invalid plugin ... received object`，
  且**整个插件树中止加载、dsh web 直接退出**（桌面症状：窗口 ERR_CONNECTION_REFUSED，
  真正的错误只在 `logs\server.err.log`）。这是 dsh-cleaner 首次上线时踩过的真实坑——
  语法/导入检查都发现不了它，装完新插件务必看一眼 server.err.log。
- 删除是**移入回收目录**，不是硬删除；确认没问题后可在面板「回收目录」里查看，
  想彻底释放空间直接清空该目录即可。
- 正在被打开的会话（agents 表里有活体）拒绝删除——先切到别的会话。
- 会话删除后，投影缓存（`storages/session_projcache.json`）里的旧行不动，
  由产品自行清理/忽略；工作区删除调用的是产品登记服务，登记变更会自动广播。
- 通道：客户端 → `POST /dsh-cleaner/api`（宿主 webServer 精确路由），与
  dsh-time-stamp / netmon 同一条经过验证的第三方通道。
