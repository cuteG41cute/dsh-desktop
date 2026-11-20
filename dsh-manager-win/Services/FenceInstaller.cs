using System;
using System.IO;
using System.Linq;
using System.Text;

namespace DshManager.Services;

/// <summary>
/// 用户级实例的围栏插件安装器：把内置的 dsh-fence 写进实例 profile，
/// 并在 cordis.patch.yml 里插入加载行（幂等）。
/// </summary>
public static class FenceInstaller
{
    public const string PluginId = "dsh-fence";

    /// <summary>安装/更新插件，并确保 profile 补丁里有加载行。</summary>
    public static (bool Ok, string Message) Ensure(RegistryEntry entry, string home)
    {
        try
        {
            var profile = Path.Combine(home, "profiles", "web");
            var target = Path.Combine(profile, "node_modules", PluginId);
            Directory.CreateDirectory(Path.Combine(target, "lib"));

            var asm = System.Reflection.Assembly.GetExecutingAssembly();
            string Read(string suffix)
            {
                var res = asm.GetManifestResourceNames()
                    .FirstOrDefault(n => n.EndsWith(suffix, StringComparison.OrdinalIgnoreCase));
                if (res == null) return null;
                using var stream = asm.GetManifestResourceStream(res);
                using var reader = new StreamReader(stream!, Encoding.UTF8);
                return reader.ReadToEnd();
            }

            var pkg = Read("dsh-fence.package.json") ?? Read("package.json");
            var index = Read("dsh-fence.lib.index.js") ?? Read("dsh-fence.index.js");
            if (pkg == null || index == null) return (false, "内置围栏插件资源缺失");
            File.WriteAllText(Path.Combine(target, "package.json"), pkg, new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(target, "lib", "index.js"), index, new UTF8Encoding(false));

            var patchPath = Path.Combine(profile, "cordis.patch.yml");
            var patch = File.Exists(patchPath) ? File.ReadAllText(patchPath) : "# dsh profile patch\n";
            if (!patch.Contains("id: " + PluginId, StringComparison.Ordinal))
            {
                if (File.Exists(patchPath))
                    File.Copy(patchPath, patchPath + ".bak-fence-" + DateTime.Now.ToString("yyyyMMdd-HHmmss"), true);
                if (!patch.EndsWith("\n")) patch += "\n";
                patch += "\n# ==== dsh-fence (installed by dsh-manager) ====\n" +
                         "- insert:\n" +
                         "    - id: " + PluginId + "\n" +
                         "      name: '" + PluginId + "'\n" +
                         "      inject: [ workspaceRegistry ]\n";
                File.WriteAllText(patchPath, patch, new UTF8Encoding(false));
            }

            return (true, "围栏插件就绪：" + target);
        }
        catch (Exception ex) { return (false, "围栏插件安装失败：" + ex.Message); }
    }
}
