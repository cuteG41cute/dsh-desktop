"ran at " + (Get-Date -Format "HH:mm:ss") + " session=" + (Get-Process -Id $PID).SessionId | Out-File C:\Users\User\probe_task.txt -Encoding UTF8
Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { $_ | Add-Member -NotePropertyName x -NotePropertyValue 1 -PassThru } | Out-Null
Add-Content C:\Users\User\probe_task.txt -Encoding UTF8 -Value ("mgr=" + (@(Get-Process DshManager -ErrorAction SilentlyContinue).Count))
