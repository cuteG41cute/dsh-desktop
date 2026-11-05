$cmd = Get-Command Set-DisplayResolution -ErrorAction SilentlyContinue
Write-Output ('cmdlet=' + $(if($cmd){'yes'}else{'no'}))
if ($cmd) { try { Set-DisplayResolution -Width 1600 -Height 900 -ErrorAction Stop; Write-Output 'set ok' } catch { Write-Output ('set fail: ' + $_.Exception.Message) } }
Write-Output ('screen=' + ((Get-CimInstance Win32_VideoController | Select-Object -First 1).CurrentHorizontalResolution))
