$again = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*agent.ps1*' }
Write-Output ('agents_now=' + (@($again).Count))
