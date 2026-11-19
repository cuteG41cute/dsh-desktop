using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;

namespace DshManager.Services;

public sealed record TaskLogEntry(DateTime At, string Type, string Message, string Detail);

public static class TaskLog
{
    private static string FilePath => Path.Combine(ProjectCatalog.ManagerDataDir, "tasks.jsonl");

    public static void Append(string type, string message, string detail = "")
    {
        try
        {
            Directory.CreateDirectory(ProjectCatalog.ManagerDataDir);
            var node = new JsonObject
            {
                ["at"] = DateTime.Now.ToString("o"),
                ["type"] = type,
                ["message"] = message,
                ["detail"] = detail,
            };
            File.AppendAllText(FilePath, node.ToJsonString() + "\n", new UTF8Encoding(false));
        }
        catch { }
    }

    public static List<TaskLogEntry> Load(int max = 200)
    {
        try
        {
            if (!File.Exists(FilePath)) return new List<TaskLogEntry>();
            var lines = File.ReadAllLines(FilePath).Where(l => l.Trim().Length > 0).TakeLast(max);
            var list = new List<TaskLogEntry>();
            foreach (var line in lines)
            {
                try
                {
                    var n = JsonNode.Parse(line);
                    if (n == null) continue;
                    list.Add(new TaskLogEntry(
                        DateTime.TryParse(n["at"]?.GetValue<string>(), out var at) ? at : DateTime.MinValue,
                        n["type"]?.GetValue<string>() ?? "info",
                        n["message"]?.GetValue<string>() ?? "",
                        n["detail"]?.GetValue<string>() ?? ""));
                }
                catch { }
            }
            return list.OrderByDescending(x => x.At).ToList();
        }
        catch { return new List<TaskLogEntry>(); }
    }
}
