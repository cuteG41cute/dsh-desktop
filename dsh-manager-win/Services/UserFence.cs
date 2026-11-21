using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace DshManager.Services;

/// <summary>
/// 专用低权限 Windows 用户围栏：实例以独立本地用户运行，NTFS 提供读写隔离，
/// 回环网络正常（管理器可直接访问 127.0.0.1）。
/// </summary>
public static class UserFence
{
    public const string UserName = "dshfence";
    private const uint LOGON_WITH_PROFILE = 0x00000001;
    private const uint CREATE_UNICODE_ENVIRONMENT = 0x00000400;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct STARTUPINFO
    {
        public int cb;
        public string lpReserved, lpDesktop, lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PROCESS_INFORMATION
    {
        public IntPtr hProcess, hThread;
        public int dwProcessId, dwThreadId;
    }

    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CreateProcessWithLogonW(
        string user, string domain, string password, uint logonFlags,
        string applicationName, string commandLine, uint creationFlags,
        IntPtr environment, string currentDirectory,
        ref STARTUPINFO startupInfo, out PROCESS_INFORMATION processInfo);

    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr h);

    private static string CredPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "dsh-manager", "fence-user.dat");

    /// <summary>读取或生成围栏用户的凭据（DPAPI 加密保存）。</summary>
    public static (string User, string Password) Credentials()
    {
        try
        {
            if (File.Exists(CredPath))
            {
                var raw = ProtectedData.Unprotect(File.ReadAllBytes(CredPath), null, DataProtectionScope.CurrentUser);
                var parts = Encoding.UTF8.GetString(raw).Split('\n', 2);
                if (parts.Length == 2) return (parts[0], parts[1]);
            }
        }
        catch { }
        var pass = "DshFence-" + Convert.ToHexString(RandomNumberGenerator.GetBytes(12)) + "!";
        SaveCredentials(UserName, pass);
        return (UserName, pass);
    }

    public static void SaveCredentials(string user, string password)
    {
        var dir = Path.GetDirectoryName(CredPath)!;
        Directory.CreateDirectory(dir);
        var data = ProtectedData.Protect(Encoding.UTF8.GetBytes(user + "\n" + password), null,
            DataProtectionScope.CurrentUser);
        File.WriteAllBytes(CredPath, data);
    }

    /// <summary>提升权限创建用户（由 --fence-user-setup 调起）。</summary>
    public static (bool Ok, string Message) CreateUserElevated(string user, string password)
    {
        try
        {
            var psi = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath ?? "DshManager.exe")
            {
                UseShellExecute = true,
                Verb = "runas",
            };
            psi.ArgumentList.Add("--fence-user-setup");
            psi.ArgumentList.Add(user);
            psi.ArgumentList.Add(password);
            using var p = System.Diagnostics.Process.Start(psi);
            if (p == null) return (false, "无法启动提权进程");
            p.WaitForExit(120000);
            return (p.ExitCode == 0, "exit " + p.ExitCode);
        }
        catch (Exception ex) { return (false, ex.Message); }
    }

    /// <summary>真正创建用户（提权进程内调用）。</summary>
    public static (bool Ok, string Message) CreateUser(string user, string password)
    {
        try
        {
            var add = RunTool("net.exe", "user", user, password, "/add");
            if (!add.Ok && !add.Message.Contains("already", StringComparison.OrdinalIgnoreCase))
                return (false, "net user /add 失败：" + add.Message);
            RunTool("net.exe", "localgroup", "Users", user, "/add");
            return (true, "用户就绪");
        }
        catch (Exception ex) { return (false, ex.Message); }
    }

    public static (bool Ok, string Message) GrantDirectory(string dir)
    {
        try
        {
            Directory.CreateDirectory(dir);
            var r = RunTool("icacls.exe", dir, "/grant", UserName + ":(OI)(CI)M", "/Q");
            return (r.Ok, r.Ok ? "已授权" : r.Message);
        }
        catch (Exception ex) { return (false, ex.Message); }
    }

    public static (bool Ok, int Pid, string Message) Start(string commandLine, string cwd, string environmentBlock)
    {
        var (user, pass) = Credentials();
        var si = new STARTUPINFO { cb = Marshal.SizeOf<STARTUPINFO>() };
        IntPtr env = string.IsNullOrEmpty(environmentBlock) ? IntPtr.Zero : Marshal.StringToHGlobalUni(environmentBlock);
        try
        {
            var ok = CreateProcessWithLogonW(user, ".", pass, LOGON_WITH_PROFILE,
                null, commandLine, CREATE_UNICODE_ENVIRONMENT, env, cwd, ref si, out var pi);
            if (!ok)
            {
                var err = Marshal.GetLastWin32Error();
                return (false, 0, "CreateProcessWithLogonW 失败：" + err);
            }
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            return (true, pi.dwProcessId, "ok");
        }
        catch (Exception ex) { return (false, 0, ex.Message); }
        finally { if (env != IntPtr.Zero) Marshal.FreeHGlobal(env); }
    }

    private static (bool Ok, string Message) RunTool(string exe, params string[] args)
    {
        var psi = new System.Diagnostics.ProcessStartInfo(exe)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var a in args) psi.ArgumentList.Add(a);
        using var p = System.Diagnostics.Process.Start(psi)!;
        var output = p.StandardOutput.ReadToEnd() + p.StandardError.ReadToEnd();
        p.WaitForExit(30000);
        return (p.ExitCode == 0, output.Trim());
    }
}
