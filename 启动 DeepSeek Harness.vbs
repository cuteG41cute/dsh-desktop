' DeepSeek Harness - silent desktop launcher (no console window at all).
' Double-click this file, or point a shortcut at it.
' It starts launcher.ps1 in a hidden window and returns immediately.
Option Explicit

Dim fso, shell, root, cmdLine
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
cmdLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & root & "\launcher.ps1"""

' 0 = hidden window, False = do not wait
shell.Run cmdLine, 0, False
