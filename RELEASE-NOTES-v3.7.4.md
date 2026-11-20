# dsh-manager 3.7.4

## 存储 BOM 守卫

11/20 的「服务起来了但没有工作区和会话」事故根因：`~/.dsh/storages/workspace.json` 被写入了 UTF-8 BOM，而 DSH 的 JSON 存储用 `JSON.parse` 直接读取、不剥 BOM，重启后 workspace 存储域以 `malformed-medium` 失败。

本版加固：

- 读取 `workspace.json` 时自动剥离 BOM（项目列表 / 导出 / 导入都不再被 BOM 卡住）；
- 新增 `--storage-check [home]`：检查 `storages/*.json` 的 BOM 与可解析性；
- 新增 `--storage-repair [home]`：对带 BOM 的文件先备份、再改写成无 BOM；
- 导入写注册表后做**写后自检**，解析失败自动用备份恢复。

用法：

```
DshManager.exe --storage-check
DshManager.exe --storage-repair
```

（修复前请先停止正在运行的 DSH 实例，避免它在内存里持有旧状态。）

## Linux

同一处读取已改为 `utf-8-sig`，Linux 版 deb 仍需在虚拟机恢复后构建。
