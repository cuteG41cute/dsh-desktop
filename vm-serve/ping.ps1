$alive = Test-Path 'C:\Users\User\agent.alive'
Write-Output ("alive=" + $alive)
if ($alive) {
  Set-Content 'C:\Users\User\req.txt' (@('pid','ls C:\Users\User\AppData\Local\dsh-manager\instances') -join "`r`n") -Encoding UTF8
  Start-Sleep -Seconds 4
  Write-Output ('res=' + ((Get-Content 'C:\Users\User\res.txt' -ErrorAction SilentlyContinue) -join ' | '))
}
