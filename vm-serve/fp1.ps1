Write-Output ('port3081=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
Write-Output ('log=' + ((Get-Content 'C:\Users\User\fakepage.log' -ErrorAction SilentlyContinue) -join ' | '))
try { $r = Invoke-WebRequest 'http://127.0.0.1:3081/' -UseBasicParsing -TimeoutSec 8; Write-Output ('page=' + $r.StatusCode + ' len=' + $r.RawContentLength) } catch { Write-Output ('page FAILED: ' + $_.Exception.Message) }
