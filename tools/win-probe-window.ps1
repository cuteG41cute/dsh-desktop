[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinProbe {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int max);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int max);
    public static void Dump(string prefix) {
        EnumWindows((h, l) => {
            var sb = new StringBuilder(512);
            GetWindowTextW(h, sb, 512);
            var t = sb.ToString();
            if (!t.StartsWith(prefix)) return true;
            var cb = new StringBuilder(256);
            GetClassNameW(h, cb, 256);
            RECT r;
            bool ok = GetWindowRect(h, out r);
            Console.WriteLine("hwnd=0x{0:X} class={1} ok={2} rect=({3},{4})-({5},{6}) title={7}",
                h.ToInt64(), cb, ok, r.Left, r.Top, r.Right, r.Bottom, t);
            return true;
        }, IntPtr.Zero);
    }
}
"@
Write-Host "screen: $([System.Windows.Forms.Screen]::PrimaryScreen.Bounds)"
[WinProbe]::Dump('DeepSeek Harness')
