$ProgressPreference='SilentlyContinue'
try { $r = Invoke-WebRequest 'https://nodejs.org/dist/index.json' -Method Head -TimeoutSec 15 -UseBasicParsing; Write-Output ('nodejs.org=' + $r.StatusCode) } catch { Write-Output ('nodejs.org FAILED: ' + $_.Exception.Message) }
try { $r2 = Invoke-WebRequest 'https://github.com' -Method Head -TimeoutSec 15 -UseBasicParsing; Write-Output ('github=' + $r2.StatusCode) } catch { Write-Output ('github FAILED: ' + $_.Exception.Message) }
