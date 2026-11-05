$inst = 'C:\Users\User\AppData\Local\dsh-manager\instances\vmtest'
Write-Output ("exists=" + (Test-Path $inst))
if (Test-Path $inst) {
  Write-Output ("kids=" + (@(Get-ChildItem $inst -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
  $app = Join-Path $inst 'app'
  if (Test-Path $app) {
    Write-Output ("app_size_MB=" + [math]::Round((Get-ChildItem $app -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB,1))
    Write-Output ("app_kids=" + (@(Get-ChildItem $app -ErrorAction SilentlyContinue | Select-Object -First 10 -ExpandProperty Name) -join ','))
  }
}
Write-Output ("git_procs=" + (@(Get-Process git,node,npm -ErrorAction SilentlyContinue | ForEach-Object { $_.ProcessName }) -join ','))
Write-Output ("mgr=" + (@(Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { "$($_.Id)/$($_.SessionId)" }) -join ';'))
Write-Output ("instances=" + (@(Get-ChildItem 'C:\Users\User\AppData\Local\dsh-manager\instances' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
Write-Output ("registry=" + (Get-Content 'C:\Users\User\AppData\Local\dsh-manager\instances.json' -Raw -ErrorAction SilentlyContinue))
