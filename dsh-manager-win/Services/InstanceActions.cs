using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;

namespace DshManager.Services;

/// <summary>更新 / 修复 / 卸载三个动作。规则按「这个安装是谁的」区分：
/// 管理器创建的可以直接重装/删除；系统安装（npx / pi-node / 全局）只做检查与提示，
/// 不动用户自己的 npm 环境。</summary>
public static class InstanceActions
{
    public static bool IsManaged(DshInstance inst)
    {
        var reg = InstanceRegistry.Load().Find(e => string.Equals(
            Path.GetFullPath(e.Dir ?? ""), Path.GetFullPath(inst.Dir ?? ""), StringComparison.OrdinalIgnoreCase));
        return reg != null;
    }

    /// <summary>更新：管理器创建的实例直接用 npm 重装最新版；其它安装给出手动命令。</summary>
    public static async Task<(bool Ok, string Message)> UpdateAsync(DshInstance inst, Action<string> log, string version = "latest")
    {
        if (!IsManaged(inst))
        {
            return (false, "这是系统安装（" + inst.Source + "），管理器不替你改它。"
                           + " 更新请在命令行执行：npm install -g @deepseek-ai/dsh@latest");
        }
        if (inst.Running) DshHost.Stop(inst, out _);
        var target = string.IsNullOrWhiteSpace(version) ? "latest" : version;
        var (ok, msg) = await InstanceInstaller.InstallAsync(inst.Dir, target, log, inst.Port);
        return (ok, ok ? "已切到 dsh " + target + "；重启服务后生效" : msg);
    }

    /// <summary>修复：检查入口/Node，缺什么补什么（管理器创建的会重装依赖）。</summary>
    public static async Task<(bool Ok, string Message)> RepairAsync(DshInstance inst, Action<string> log)
    {
        if (!File.Exists(inst.Entry)) return (false, "入口不存在：" + inst.Entry);
        if (string.IsNullOrEmpty(inst.NodeExe) || !File.Exists(inst.NodeExe))
            return (false, "找不到 node.exe（PATH 上没有，安装目录里也没有）");

        // 跑一次 --version 证明能起来
        try
        {
            var psi = new ProcessStartInfo(inst.NodeExe)
            {
                RedirectStandardOutput = true, RedirectStandardError = true,
                UseShellExecute = false, CreateNoWindow = true,
            };
            psi.ArgumentList.Add(inst.Entry);
            psi.ArgumentList.Add("--version");
            using var p = Process.Start(psi);
            var output = p.StandardOutput.ReadToEnd().Trim();
            var err = p.StandardError.ReadToEnd().Trim();
            p.WaitForExit(20000);
            log("node " + Path.GetFileName(inst.NodeExe) + " → " + (output.Length > 0 ? output : err));
            if (p.ExitCode != 0) return (false, "启动自检失败（exit " + p.ExitCode + "）：" + err);
        }
        catch (Exception ex)
        {
            return (false, "启动自检异常：" + ex.Message);
        }

        if (IsManaged(inst))
        {
            var modules = Path.Combine(inst.Dir, "node_modules");
            if (!Directory.Exists(modules))
            {
                log("依赖目录缺失，重新安装…");
                return await InstanceInstaller.InstallAsync(inst.Dir, "latest", log, inst.Port);
            }
        }
        return (true, "自检通过：入口可执行（dsh " + inst.DshVersion + "）");
    }

    /// <summary>卸载：管理器创建的实例可以删目录；系统安装只允许「从列表移除」的提示。</summary>
    public static (bool Ok, string Message) Uninstall(DshInstance inst, bool deleteDir)
    {
        if (!IsManaged(inst))
            return (false, "这是系统安装（" + inst.Source + "），管理器不删它。"
                           + " 需要清理请在文件管理器中操作，或 npm uninstall -g @deepseek-ai/dsh");
        if (inst.Running) DshHost.Stop(inst, out _);
        if (deleteDir)
        {
            // 刚 taskkill 完时 node 还握着 node_modules 里的文件句柄，立刻删会「删一半」。
            // 等端口真正不再监听（最多 15 秒）再动手。
            for (var i = 0; i < 30; i++)
            {
                DshDiscovery.InvalidateListeners();
                DshDiscovery.Probe(inst);
                if (!inst.Running) break;
                System.Threading.Thread.Sleep(500);
            }
        }
        if (deleteDir)
        {
            try
            {
                if (Directory.Exists(inst.Dir)) DeleteDirectoryRobust(inst.Dir);
            }
            catch (Exception ex)
            {
                return (false, "删目录失败（可能有进程占用）：" + ex.Message);
            }
        }
        InstanceRegistry.RemoveByDir(inst.Dir);
        return (true, deleteDir ? "已删除实例目录并从登记表移除" : "已从登记表移除（目录保留）");
    }

    /// <summary>
    /// 稳妥地递归删除目录：node_modules / pnpm-store 里有只读文件、深路径和被占用的句柄，
    /// 一句 Directory.Delete 经常删一半就抛异常（VM 实测：剩下 app/pnpm-store/tools 834MB）。
    /// 这里清只读、重试多次，最后用长路径前缀再试一遍。
    /// </summary>
    private static void DeleteDirectoryRobust(string dir)
    {
        var full = Path.GetFullPath(dir);
        for (var attempt = 0; attempt < 4; attempt++)
        {
            try
            {
                foreach (var f in Directory.EnumerateFiles(full, "*", SearchOption.AllDirectories))
                {
                    try
                    {
                        var attrs = File.GetAttributes(f);
                        if ((attrs & FileAttributes.ReadOnly) != 0)
                            File.SetAttributes(f, attrs & ~FileAttributes.ReadOnly);
                    }
                    catch { }
                }
            }
            catch { }
            try { Directory.Delete(full, true); return; }
            catch
            {
                System.Threading.Thread.Sleep(700);
            }
        }
        // 长路径兜底（node_modules 的嵌套路径很容易超过 MAX_PATH）
        var longPath = full.StartsWith(@"\\?\", StringComparison.Ordinal) ? full : @"\\?\" + full;
        try
        {
            foreach (var f in Directory.EnumerateFiles(longPath, "*", SearchOption.AllDirectories))
            {
                try { File.SetAttributes(f, FileAttributes.Normal); } catch { }
            }
        }
        catch { }
        Directory.Delete(longPath, true);
    }
}
