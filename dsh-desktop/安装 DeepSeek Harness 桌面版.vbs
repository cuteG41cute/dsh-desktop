' 安装 DeepSeek Harness 桌面版（自适应安装程序入口，无控制台窗口）
' Double-click this file to run the installer silently (GUI dialogs, no console).
Option Explicit

Dim fso, shell, root, cmdLine
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
cmdLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & root & "\installer.ps1"""

' 0 = hidden window, False = do not wait
shell.Run cmdLine, 0, False
