Write-Output ("agent_png=" + (Test-Path C:\Users\User\agenttest.png))
Write-Output ("shot_done=" + (Get-Content C:\Users\User\shot.done -ErrorAction SilentlyContinue))
$inst = 'C:\Users\User\AppData\Local\dsh-manager\instances\vmtest'
Write-Output ("instance_dir=" + (Test-Path $inst))
if (Test-Path $inst) {
  $kids = @(Get-ChildItem $inst -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
  Write-Output ("kids=" + ($kids -join ','))
  if (Test-Path (Join-Path $inst 'node\node.exe')) { Write-Output ("node=" + (& (Join-Path $inst 'node\node.exe') --version)) }
  if (Test-Path (Join-Path $inst 'app')) { Write-Output ("app_kids=" + (@(Get-ChildItem (Join-Path $inst 'app') -ErrorAction SilentlyContinue | Select-Object -First 8 -ExpandProperty Name) -join ',')) }
}
Write-Output ("mgr=" + (@(Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { "$($_.Id)/$($_.SessionId)" }) -join ';'))
