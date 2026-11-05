$p = 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-a-2'
Write-Output ('kids=' + (@(Get-ChildItem $p -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
Write-Output ('MB=' + [math]::Round((Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB,1))
Write-Output ('tmpzip=' + (@(Get-ChildItem $env:TEMP -Filter 'dsh-node-*' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name + ':' + [math]::Round($_.Length/1MB,1) }) -join ','))
Write-Output ('node_proc=' + (@(Get-Process node -ErrorAction SilentlyContinue).Count))
