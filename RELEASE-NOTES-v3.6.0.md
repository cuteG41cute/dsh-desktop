# dsh-manager 3.6.0

新增「项目迁移」：把一台机器上 DSH 的项目（目录 + 会话记录 + 注册表条目）打包成 `.dshproj`，在另一台机器导入。

## 用什么打包

一个 `.dshproj` 是 tar.gz，里面：

```
manifest.json               项目标题、源路径、时间
state/workspace-entry.json  原注册表条目（备份用）
sessions/<projectKey>/      该项目的全部会话记录
project/...                 项目文件（可选，跳过 node_modules/.git/bin/obj/dist/.vs）
```

`projectKey` 用 DSH 自己的规则实现（分隔符折叠成 `-`，空格等转 `~XXXX`，前后 `--`），保证导入到不同路径时能把会话目录正确重建。

## 界面

「管理器功能」页底部新增 **项目迁移** 区块：

- 项目下拉（读 `~/.dsh/storages/workspace.json`，显示会话数）；
- **导出…** → 选保存位置，生成 `.dshproj`；
- **导入…** → 选包 + 选目标目录，自动解包、复制会话、写注册表（先备份 `workspace.json`）；
- 状态行显示进度/结果。

## 实测

| 平台 | 操作 | 结果 |
| --- | --- | --- |
| Windows | 导出 `test` 项目 | 2.1 MB（11 会话的项目更大） |
| Windows | 导入到临时目录 | 注册表新增条目、3 个会话目录就位 |
| Linux VM | 导出 + 导入 `default-workspace` | 0.1 MB，导入后注册表出现新条目（1 会话） |

## 注意

- 导入完成后需要**重启该实例**，项目才会出现在侧栏列表（DSH 启动时读注册表）；
- 会话记录按新路径重新编码目录名；旧路径的会话不会被修改；
- 项目文件默认包含，可在界面取消勾选只搬「会话」；
- 存储器里的 memory-db、file-history 暂未打包（下一步可加）。
