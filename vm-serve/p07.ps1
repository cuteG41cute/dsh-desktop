$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
Write-Output ('dirs=' + (@(Get-ChildItem $root -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
foreach ($d in @('dsh-a','dsh-new')) {
  $p = Join-Path $root $d
  if (Test-Path $p) {
    Write-Output ($d + ' kids=' + (@(Get-ChildItem $p -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
    if (Test-Path (Join-Path $p 'app')) { Write-Output ($d + ' app_kids=' + (@(Get-ChildItem (Join-Path $p 'app') -ErrorAction SilentlyContinue | Select-Object -First 6 -ExpandProperty Name) -join ',')) }
  }
}
Write-Output ('node_proc=' + (@(Get-Process node -ErrorAction SilentlyContinue).Count))
Write-Output ('git_proc=' + (@(Get-Process git -ErrorAction SilentlyContinue).Count))
