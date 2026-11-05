$p = 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-a'
Write-Output ('exists=' + (Test-Path $p))
Write-Output ('kids=' + (@(Get-ChildItem $p -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
Write-Output ('MB=' + [math]::Round((Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB,1))
Write-Output ('app_kids=' + (@(Get-ChildItem (Join-Path $p 'app') -ErrorAction SilentlyContinue | Select-Object -First 8 -ExpandProperty Name) -join ','))
Write-Output ('node_proc=' + (@(Get-Process node -ErrorAction SilentlyContinue).Count))
Write-Output ('git_proc=' + (@(Get-Process git -ErrorAction SilentlyContinue).Count))
Write-Output ('pgit=' + (@(Get-Process pnpm -ErrorAction SilentlyContinue).Count))
