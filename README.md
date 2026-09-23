# DeepSeek Harness 工作区

本仓库是 **DeepSeek Harness 桌面版**的源码与打包仓库
（GitHub：<https://github.com/cuteG41cute/dsh-desktop>）。

> 这个文件夹同时也是本机的 DeepSeek Harness 工作目录，因此除了仓库内容外，
> 还有几个由 harness / 其他项目生成的目录（见下表，均已 gitignore）。

## 目录一览

| 路径 | 内容 |
| --- | --- |
| **`dsh-desktop/`** | **桌面版的全部内容**：Windows（WebView2 包装程序 + 启动器 + 安装程序）与 Linux（GTK/WebKitGTK）版源码、打包脚本、构建产物 `dist/`。**桌面版相关的开发都在这里进行。** |
| `backup/dsh-file-history/` | 「改前自动备份」插件（随本仓库一起管理的小项目） |
| `share/`、`skills/`、`api/` | DeepSeek Harness 运行时生成（插件/技能分发目录等，已 gitignore） |
| `dsh-time-stamp/` | 时间戳插件（**独立 git 仓库**，不在本仓库内） |
| `menmory logic/`、`.dsh/` | 用户与 harness 的运行数据 |
| `.tmp/` | 本机构建工具缓存（WiX 工具链等，已 gitignore） |

## 快速入口

- **桌面版文档**：[`dsh-desktop/README.md`](dsh-desktop/README.md)（功能、目录结构、打包、常见问题）
- **启动**：双击 `dsh-desktop/启动 DeepSeek Harness.vbs`；安装后使用桌面上的「DeepSeek Harness」快捷方式
- **安装包**：`dsh-desktop/dist/`，或下载 [Releases](https://github.com/cuteG41cute/dsh-desktop/releases)
- **Linux 版**：`dsh-desktop/linux/README.md`
- **打包**：`dsh-desktop/msi/build-msi.ps1`（Windows MSI）、`dsh-desktop/linux/build/build-linux.py`（deb + tar.gz）

## 许可

MIT，见 [LICENSE](LICENSE)。
