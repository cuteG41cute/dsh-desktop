using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;

namespace DshManager.Services;

/// <summary>
/// DSH 单文件存储（workspace.json 等）的健康检查。
/// DSH 用 JSON.parse 直接读文件、不剥 BOM；一旦文件带 UTF-8 BOM，
/// 该存储域会以 malformed-medium 失败（表现为「有服务但没有工作区/会话」）。
/// </summary>
public static class StorageHealth
{
    public sealed record FileReport(string Path, bool HasBom, bool Parses, string Message);

    /// <summary>检查一个 DSH home 下 storages/*.json 的 BOM 与可解析性。</summary>
    public static List<FileReport> Check(string dshHome)
    {
        var reports = new List<FileReport>();
        var dir = Path.Combine(dshHome, "storages");
        if (!Directory.Exists(dir)) return reports;
        foreach (var file in Directory.GetFiles(dir, "*.json"))
        {
            var bytes = File.ReadAllBytes(file);
            var hasBom = bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF;
            var text = Encoding.UTF8.GetString(bytes);
            var bomStripped = hasBom ? text.Substring(1) : text;
            var parses = true;
            var message = "";
            try
            {
                var node = JsonNode.Parse(bomStripped);
                message = node == null ? "null" : "ok";
            }
            catch (Exception ex)
            {
                parses = false;
                message = ex.Message;
            }
            reports.Add(new FileReport(file, hasBom, parses, message));
        }
        return reports.OrderBy(r => r.Path).ToList();
    }

    /// <summary>把带 BOM 的文件改写成无 BOM（先备份为 .bom-bak-yyyyMMdd-HHmmss）。</summary>
    public static (bool Ok, string Message) RepairBom(string file)
    {
        try
        {
            var bytes = File.ReadAllBytes(file);
            var hasBom = bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF;
            if (!hasBom) return (true, "没有 BOM：" + Path.GetFileName(file));
            var text = Encoding.UTF8.GetString(bytes);
            var backup = file + ".bom-bak-" + DateTime.Now.ToString("yyyyMMdd-HHmmss");
            File.Copy(file, backup, true);
            File.WriteAllText(file, text.Substring(1), new UTF8Encoding(false));
            return (true, "已修复 " + Path.GetFileName(file) + "（备份 " + Path.GetFileName(backup) + "）");
        }
        catch (Exception ex) { return (false, "修复失败：" + ex.Message); }
    }
}
