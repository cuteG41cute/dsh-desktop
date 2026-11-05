$inst = 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new'
Write-Output ('exists=' + (Test-Path $inst))
try { Remove-Item $inst -Recurse -Force -ErrorAction Stop; Write-Output 'plain delete OK' }
catch { Write-Output ('plain delete FAILED: ' + $_.Exception.Message) }
if (Test-Path $inst) {
  $n = 0
  try {
    Get-ChildItem $inst -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
      try { if ($_.IsReadOnly) { $_.IsReadOnly = $false; $n++ } } catch {}
    }
  } catch {}
  Write-Output ('cleared_readonly=' + $n)
  try { Remove-Item $inst -Recurse -Force -ErrorAction Stop; Write-Output 'retry delete OK' }
  catch { Write-Output ('retry FAILED: ' + $_.Exception.Message) }
}
Write-Output ('exists_after=' + (Test-Path $inst))
