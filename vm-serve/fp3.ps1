try { $r = Invoke-WebRequest 'http://127.0.0.1:3081/' -UseBasicParsing -TimeoutSec 8; Write-Output ('len=' + $r.RawContentLength + ' hasImg=' + ($r.Content -like '*#im{*')) } catch { Write-Output ('FAILED ' + $_.Exception.Message) }
Write-Output ('log_tail=' + ((Get-Content 'C:\Users\User\fakepage.log' -Tail 4 -ErrorAction SilentlyContinue) -join ' | '))
