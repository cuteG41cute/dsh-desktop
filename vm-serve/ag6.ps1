$src = Get-Content 'C:\Users\User\agent.ps1' -Raw
$errs = $null
$null = [System.Management.Automation.PSParser]::Tokenize($src, [ref]$errs)
Write-Output ('parse_errors=' + (@($errs).Count))
if ($errs) { $errs | Select-Object -First 3 | ForEach-Object { Write-Output ('  ' + $_.Message) } }

schtasks /end /tn dshagent 2>&1 | Out-Null
schtasks /delete /tn dshagent /f 2>&1 | Out-Null
schtasks /create /tn dshagent /tr C:\Users\User\agent.cmd /sc once /st 00:00 /ru User /it /f 2>&1 | Out-Null
schtasks /run /tn dshagent 2>&1 | Out-Null
Start-Sleep -Seconds 6

$t = schtasks /query /tn dshagent /v /fo list 2>&1
($t | Select-String 'Status|Last Result|Last Run') | ForEach-Object { Write-Output $_.Line.Trim() }
$p = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*agent.ps1*' }
Write-Output ('agents=' + (@($p).Count))
