$t = schtasks /query /tn dshagent /v /fo list 2>&1
($t | Select-String "Status|Last Run|Last Result|Task To Run") | ForEach-Object { Write-Output $_.Line.Trim() }
Write-Output ('--- session ---')
Write-Output ((qwinsta) -join "`n")
