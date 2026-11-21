using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;

namespace DshManager.Services;

/// <summary>
/// Windows AppContainer 围栏：创建/复用 AppContainer 配置、授 ACL、以受限令牌启动进程。
/// 说明：AppContainer 默认禁止回环，管理器要访问实例需要一次性管理员执行回环豁免
/// （CheckNetIsolation LoopbackExempt）。
/// </summary>
public static class AppContainerFence
{
    private const int PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009;
    private const uint EXTENDED_STARTUPINFO_PRESENT = 0x00080000;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct STARTUPINFO
    {
        public int cb;
        public string lpReserved, lpDesktop, lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct STARTUPINFOEX { public STARTUPINFO StartupInfo; public IntPtr lpAttributeList; }

    [StructLayout(LayoutKind.Sequential)]
    private struct SECURITY_CAPABILITIES { public IntPtr AppContainerSid; public IntPtr Capabilities; public int CapabilityCount; public int Reserved; }

    [StructLayout(LayoutKind.Sequential)]
    private struct SID_AND_ATTRIBUTES { public IntPtr Sid; public uint Attributes; }

    [StructLayout(LayoutKind.Sequential)]
    private struct PROCESS_INFORMATION { public IntPtr hProcess, hThread; public int dwProcessId, dwThreadId; }

    [DllImport("userenv.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int CreateAppContainerProfile(string name, string displayName, string description,
        IntPtr capabilities, uint capabilityCount, out IntPtr sid);
    [DllImport("userenv.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int DeriveAppContainerSidFromAppContainerName(string name, out IntPtr sid);
    [DllImport("userenv.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int DeleteAppContainerProfile(string name);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool ConvertSidToStringSid(IntPtr sid, out IntPtr str);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool ConvertStringSidToSid(string sid, out IntPtr pSid);
    [DllImport("FirewallAPI.dll", SetLastError = true)]
    private static extern uint NetworkIsolationSetAppContainerConfig(uint count,
        [In] SID_AND_ATTRIBUTES[] entries);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool InitializeProcThreadAttributeList(IntPtr list, int count, int flags, ref IntPtr size);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool UpdateProcThreadAttribute(IntPtr list, uint flags, IntPtr attr, IntPtr value,
        IntPtr size, IntPtr prev, IntPtr ret);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern void DeleteProcThreadAttributeList(IntPtr list);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CreateProcess(string app, string cmd, IntPtr pa, IntPtr ta, bool inherit,
        uint flags, IntPtr env, string cwd, ref STARTUPINFOEX si, out PROCESS_INFORMATION pi);
    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetHandleInformation(IntPtr hObject, uint dwMask, uint dwFlags);

    public static bool MakeInheritable(IntPtr handle) => SetHandleInformation(handle, 1, 1);

    public static string ProfileNameFor(string instanceId)
    {
        var safe = string.Concat(instanceId.Where(ch => (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') || ch == '-'));
        return "dsh-manager-fence-" + (safe.Length == 0 ? "instance" : safe);
    }

    /// <summary>创建/复用 AppContainer 配置，返回 SID 字符串。</summary>
    public static (bool Ok, string Sid, string Message) EnsureProfile(string profileName)
    {
        IntPtr sid = IntPtr.Zero;
        var hr = CreateAppContainerProfile(profileName, profileName, "dsh-manager user-tier instance", IntPtr.Zero, 0, out sid);
        if (hr != 0)
        {
            hr = DeriveAppContainerSidFromAppContainerName(profileName, out sid);
            if (hr != 0) return (false, "", $"AppContainer 配置创建失败：0x{hr:X8}");
        }
        IntPtr str;
        if (!ConvertSidToStringSid(sid, out str)) return (false, "", "无法取得 AppContainer SID");
        return (true, Marshal.PtrToStringUni(str) ?? "", "ok");
    }

    /// <summary>给目录授予 AppContainer SID 的修改权限（子项继承）。</summary>
    public static (bool Ok, string Message) GrantDirectory(string dir, string sid)
    {
        try
        {
            Directory.CreateDirectory(dir);
            // 已有 ACE 就跳过（icacls 在超大目录上可能要一两分钟）
            try
            {
                var sec = new System.Security.AccessControl.DirectorySecurity(dir,
                    System.Security.AccessControl.AccessControlSections.Access);
                foreach (System.Security.AccessControl.FileSystemAccessRule rule in
                         sec.GetAccessRules(true, true, typeof(System.Security.Principal.SecurityIdentifier)))
                {
                    if (rule.IdentityReference.Value == sid
                        && (rule.FileSystemRights & System.Security.AccessControl.FileSystemRights.Modify) ==
                        System.Security.AccessControl.FileSystemRights.Modify)
                        return (true, "已授权");
                }
            }
            catch { }
            var psi = new ProcessStartInfo("icacls")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            psi.ArgumentList.Add(dir);
            psi.ArgumentList.Add("/grant");
            psi.ArgumentList.Add("*" + sid + ":(OI)(CI)M");
            psi.ArgumentList.Add("/Q");
            using var p = Process.Start(psi)!;
            p.WaitForExit(240000);
            return (p.ExitCode == 0, "icacls exit " + p.ExitCode);
        }
        catch (Exception ex) { return (false, ex.Message); }
    }

    /// <summary>给 AppContainer 添加回环豁免（需要管理员）。</summary>
    public static (bool Ok, string Message) TryLoopbackExempt(string profileName)
    {
        try
        {
            // 先给 AppContainer SID 做网络隔离豁免（未打包的 AppContainer 只认 SID，
            // CheckNetIsolation -n=<name> 对它们无效）
            var sidText = "";
            if (DeriveAppContainerSidFromAppContainerName(profileName, out var appSid) == 0)
            {
                if (ConvertSidToStringSid(appSid, out var sidPtr)) sidText = Marshal.PtrToStringUni(sidPtr) ?? "";
                var arr = new[] { new SID_AND_ATTRIBUTES { Sid = appSid, Attributes = 0 } };
                var hr = NetworkIsolationSetAppContainerConfig(1, arr);
                if (hr != 0)
                    return (false, $"NetworkIsolationSetAppContainerConfig 失败：0x{hr:X8}（SID {sidText}）");
            }
            var psi = new ProcessStartInfo("CheckNetIsolation")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            psi.ArgumentList.Add("LoopbackExempt");
            psi.ArgumentList.Add("-a");
            psi.ArgumentList.Add("-n=" + profileName);
            using var p = Process.Start(psi)!;
            var stdout = p.StandardOutput.ReadToEnd();
            p.WaitForExit(15000);
            return (p.ExitCode == 0, stdout.Trim());
        }
        catch (Exception ex) { return (false, ex.Message); }
    }

    /// <summary>以 AppContainer 受限令牌启动进程（可带 internetClient 能力）。</summary>
    public static (bool Ok, int Pid, string Message) Start(string profileName, string commandLine, string cwd,
        bool internetClient, string environmentBlock, IntPtr stdioHandle)
    {
        var ensure = EnsureProfile(profileName);
        if (!ensure.Ok) return (false, 0, ensure.Message);

        IntPtr appSid = IntPtr.Zero;
        if (DeriveAppContainerSidFromAppContainerName(profileName, out appSid) != 0)
            return (false, 0, "无法取得 AppContainer SID");

        IntPtr size = IntPtr.Zero;
        InitializeProcThreadAttributeList(IntPtr.Zero, 1, 0, ref size);
        IntPtr list = Marshal.AllocHGlobal(size);
        if (!InitializeProcThreadAttributeList(list, 1, 0, ref size))
            return (false, 0, "InitializeProcThreadAttributeList 失败");

        IntPtr capArray = IntPtr.Zero;
        var capCount = 0;
        if (internetClient && ConvertStringSidToSid("S-1-15-3-1", out var capSid))
        {
            capArray = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(SID_AND_ATTRIBUTES)));
            var sa = new SID_AND_ATTRIBUTES { Sid = capSid, Attributes = 0 };
            Marshal.StructureToPtr(sa, capArray, false);
            capCount = 1;
        }
        var caps = new SECURITY_CAPABILITIES
        {
            AppContainerSid = appSid,
            Capabilities = capArray,
            CapabilityCount = capCount,
        };
        IntPtr capsPtr = Marshal.AllocHGlobal(Marshal.SizeOf(caps));
        Marshal.StructureToPtr(caps, capsPtr, false);
        if (!UpdateProcThreadAttribute(list, 0, (IntPtr)PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                capsPtr, (IntPtr)Marshal.SizeOf(caps), IntPtr.Zero, IntPtr.Zero))
            return (false, 0, "UpdateProcThreadAttribute 失败");

        var si = new STARTUPINFOEX();
        si.StartupInfo.cb = Marshal.SizeOf(si);
        si.lpAttributeList = list;
        if (stdioHandle != IntPtr.Zero)
        {
            si.StartupInfo.dwFlags = 0x00000100; // STARTF_USESTDHANDLES
            si.StartupInfo.hStdOutput = stdioHandle;
            si.StartupInfo.hStdError = stdioHandle;
        }
        var pi = new PROCESS_INFORMATION();
        var sb = new StringBuilder(commandLine);
        IntPtr envPtr = IntPtr.Zero;
        if (!string.IsNullOrEmpty(environmentBlock))
            envPtr = Marshal.StringToHGlobalUni(environmentBlock);
        var flags = EXTENDED_STARTUPINFO_PRESENT | (envPtr != IntPtr.Zero ? 0x00000400u : 0u);
        var ok = CreateProcess(null, sb.ToString(), IntPtr.Zero, IntPtr.Zero, stdioHandle != IntPtr.Zero,
            flags, envPtr, cwd, ref si, out pi);
        if (!ok)
        {
            var err = Marshal.GetLastWin32Error();
            if (envPtr != IntPtr.Zero) Marshal.FreeHGlobal(envPtr);
            DeleteProcThreadAttributeList(list);
            Marshal.FreeHGlobal(list);
            return (false, 0, "CreateProcess 失败：" + err);
        }
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        if (envPtr != IntPtr.Zero) Marshal.FreeHGlobal(envPtr);
        DeleteProcThreadAttributeList(list);
        Marshal.FreeHGlobal(list);
        return (true, pi.dwProcessId, "ok");
    }
}
