$p = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*agent.ps1*' }
Write-Output ('agents=' + (@($p).Count))
Write-Output ('alive_time=' + (Get-Item 'C:\Users\User\agent.alive' -ErrorAction SilentlyContinue).LastWriteTime.ToString('HH:mm:ss'))
