Option Explicit

' DeepSeek Harness Desktop - MSI custom actions.
' ASCII-only (the MSI VBScript engine cannot parse UTF-16/UTF-8 BOM scripts).

Function GetDshStatus()
  Dim sh, fso, p, apd, pf, home, found, fd, subf
  Set sh = CreateObject("WScript.Shell")
  Set fso = CreateObject("Scripting.FileSystemObject")
  found = ""
  p = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\npm-cache\_npx"
  If fso.FolderExists(p) Then
    Set fd = fso.GetFolder(p)
    For Each subf In fd.SubFolders
      If fso.FileExists(subf.Path & "\node_modules\@deepseek-ai\dsh\lib\bin.js") Then
        found = subf.Path & "\node_modules\@deepseek-ai\dsh\lib\bin.js"
      End If
    Next
  End If
  If found = "" Then
    apd = sh.ExpandEnvironmentStrings("%APPDATA%")
    If fso.FileExists(apd & "\npm\node_modules\@deepseek-ai\dsh\lib\bin.js") Then found = apd & "\npm\node_modules\@deepseek-ai\dsh\lib\bin.js"
  End If
  If found = "" Then
    pf = sh.ExpandEnvironmentStrings("%ProgramFiles%")
    If fso.FileExists(pf & "\nodejs\node_modules\@deepseek-ai\dsh\lib\bin.js") Then found = pf & "\nodejs\node_modules\@deepseek-ai\dsh\lib\bin.js"
  End If
  If found = "" Then
    home = sh.ExpandEnvironmentStrings("%USERPROFILE%")
    If fso.FileExists(home & "\.dsh\profiles\node_modules\@deepseek-ai\dsh\lib\bin.js") Then found = home & "\.dsh\profiles\node_modules\@deepseek-ai\dsh\lib\bin.js"
  End If
  If found <> "" Then
    Session.Property("DSH_DETECT_STATUS") = "DeepSeek Harness detected: " & found
    Session.Property("DSH_DETECTED") = "1"
  Else
    Session.Property("DSH_DETECT_STATUS") = "DeepSeek Harness not found. Use [Help install], type a path manually, or click [Next] to skip (the app auto-detects on first launch)."
    Session.Property("DSH_DETECTED") = "0"
  End If
End Function

Function Q(p)
  If InStr(p, " ") > 0 Then
    Q = Chr(34) & p & Chr(34)
  Else
    Q = p
  End If
End Function

Function HelpInstallDsh()
  Dim sh, fso, node, npm, log, r, cmd
  Set sh = CreateObject("WScript.Shell")
  Set fso = CreateObject("Scripting.FileSystemObject")
  node = sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\nodejs\node.exe"
  If Not fso.FileExists(node) Then node = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\nodejs\node.exe"
  If Not fso.FileExists(node) Then node = ""
  If node = "" Then
    Session.Property("DSH_HELP_RESULT") = "Node.js not found. Install Node.js (https://nodejs.org) first."
    Exit Function
  End If
  npm = sh.ExpandEnvironmentStrings("%APPDATA%") & "\npm\npm.cmd"
  If Not fso.FileExists(npm) Then npm = sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\nodejs\npm.cmd"
  If Not fso.FileExists(npm) Then npm = "npm"
  log = sh.ExpandEnvironmentStrings("%TEMP%") & "\dsh-msi-npm.log"
  cmd = "cmd /c " & Q(npm) & " install -g @deepseek-ai/dsh > " & Q(log) & " 2>&1"
  On Error Resume Next
  r = sh.Run(cmd, 0, True)
  On Error GoTo 0
  If r = 0 Then
    Session.Property("DSH_HELP_RESULT") = "DeepSeek Harness installed. Click [Back] then [Next] to re-check."
  Else
    Session.Property("DSH_HELP_RESULT") = "npm install failed (exit " & r & "). See log: " & log
  End If
End Function

Function ValidateDshPath()
  Dim fso, p, cand, ok, arr, j
  Set fso = CreateObject("Scripting.FileSystemObject")
  p = Trim(Session.Property("DSH_MANUAL_PATH"))
  If Left(p, 1) = Chr(34) And Right(p, 1) = Chr(34) Then p = Mid(p, 2, Len(p) - 2)
  p = Trim(p)
  If p = "" Then
    Session.Property("DSH_PATH_ERROR") = "Please enter a path first."
    Session.Property("DSH_CONFIG_REQUIRED") = "0"
    Exit Function
  End If
  ok = ""
  If fso.FileExists(p) Then
    If LCase(fso.GetFile(p).Name) = "bin.js" Then
      ok = p
    ElseIf LCase(fso.GetFile(p).Name) = "node.exe" Then
      cand = fso.GetParentFolderName(p) & "\node_modules\@deepseek-ai\dsh\lib\bin.js"
      If fso.FileExists(cand) Then ok = cand
    End If
  ElseIf fso.FolderExists(p) Then
    arr = Array(p & "\lib\bin.js", p & "\node_modules\@deepseek-ai\dsh\lib\bin.js", p & "\@deepseek-ai\dsh\lib\bin.js", p & "\dsh\lib\bin.js")
    For j = 0 To UBound(arr)
      If fso.FileExists(arr(j)) Then ok = arr(j)
    Next
  End If
  If ok <> "" Then
    Session.Property("DSH_CONFIG_PATH") = ok
    Session.Property("DSH_CONFIG_REQUIRED") = "1"
    Session.Property("DSH_PATH_ERROR") = "Path valid; dsh-path.config will be written: " & ok
  Else
    Session.Property("DSH_CONFIG_REQUIRED") = "0"
    Session.Property("DSH_PATH_ERROR") = "No DeepSeek Harness program found at: " & p & " (click [Next] to continue anyway; the app auto-detects on launch)"
  End If
End Function

Function WriteDshConfig()
  Dim fso, dir, p, ts, data, part
  Set fso = CreateObject("Scripting.FileSystemObject")
  data = Session.Property("CustomActionData")
  dir = ""
  p = ""
  For Each part In Split(data, ";")
    If Left(part, 4) = "DIR=" Then dir = Mid(part, 5)
    If Left(part, 4) = "CFG=" Then p = Mid(part, 5)
  Next
  If dir <> "" And p <> "" Then
    Set ts = fso.CreateTextFile(dir & "dsh-path.config", True)
    ts.Write p
    ts.Close
  End If
End Function

Function RemoveDshConfig()
  Dim fso, f, data, part
  Set fso = CreateObject("Scripting.FileSystemObject")
  data = Session.Property("CustomActionData")
  f = ""
  For Each part In Split(data, ";")
    If Left(part, 4) = "DIR=" Then f = Mid(part, 5) & "dsh-path.config"
  Next
  If f <> "" Then
    If fso.FileExists(f) Then fso.DeleteFile f, True
  End If
End Function

Function RemoveShortcuts()
  Dim fso, data, part, desk, menu, d
  Set fso = CreateObject("Scripting.FileSystemObject")
  data = Session.Property("CustomActionData")
  desk = ""
  menu = ""
  For Each part In Split(data, ";")
    If Left(part, 5) = "DESK=" Then desk = Mid(part, 6)
    If Left(part, 5) = "MENU=" Then menu = Mid(part, 6)
  Next
  If desk <> "" Then
    If fso.FileExists(desk & "DeepSeek Harness.lnk") Then fso.DeleteFile desk & "DeepSeek Harness.lnk", True
  End If
  If menu <> "" Then
    If fso.FileExists(menu) Then fso.DeleteFile menu, True
    d = fso.GetParentFolderName(menu)
    If fso.FolderExists(d) Then
      If d <> "" And fso.GetFolder(d).Files.Count = 0 Then fso.DeleteFolder d, True
    End If
  End If
End Function
