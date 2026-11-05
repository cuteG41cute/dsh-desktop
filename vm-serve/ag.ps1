Write-Output ('agent_proc=' + (@(Get-Process powershell -ErrorAction SilentlyContinue).Count))
Write-Output ('req=' + (Test-Path 'C:\Users\User\req.txt'))
Write-Output ('res=' + ((Get-Content 'C:\Users\User\res.txt' -ErrorAction SilentlyContinue) -join ' | '))
Write-Output ('alive=' + (Test-Path 'C:\Users\User\agent.alive'))
