$ErrorActionPreference = 'Continue'
$log = 'C:\Users\User\diag1.out.txt'
"=== processes ===" | Set-Content $log -Encoding ASCII
Get-Process | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
    "pid=$($_.Id) sess=$($_.SessionId) title=[$($_.MainWindowTitle)] name=$($_.ProcessName)" | Add-Content $log
}
"=== enumwindows ===" | Add-Content $log
Add-Type @"
using System;using System.Text;using System.Collections.Generic;using System.Runtime.InteropServices;
public class E{
 [DllImport("user32.dll")]public static extern bool EnumWindows(EnumProc cb,IntPtr l);
 public delegate bool EnumProc(IntPtr h,IntPtr l);
 [DllImport("user32.dll")]public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)]public static extern int GetWindowTextW(IntPtr h,StringBuilder s,int m);
 [DllImport("user32.dll")]public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")]public static extern bool GetWindowRect(IntPtr h,out RECT r);
 public struct RECT{public int L,T,R,B;}
 public static List<string> All(){
  var list=new List<string>();
  EnumWindows((h,l)=>{
    var t=new StringBuilder(256);GetWindowTextW(h,t,256);
    var s=t.ToString();
    if(s.Length>0 && IsWindowVisible(h)){
      uint p;GetWindowThreadProcessId(h,out p);
      RECT r;GetWindowRect(h,out r);
      list.Add("hwnd="+h+" pid="+p+" rect="+r.L+","+r.T+","+r.R+","+r.B+" title=["+s+"]");
    }
    return true;},IntPtr.Zero);
  return list;}
}
"@
[E]::All() | ForEach-Object { $_ | Add-Content $log }
