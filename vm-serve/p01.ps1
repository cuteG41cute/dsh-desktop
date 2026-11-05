$inst = 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new'
Write-Output ('exists=' + (Test-Path $inst))
if (Test-Path $inst) {
  Write-Output ('kids=' + (@(Get-ChildItem $inst -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
  Write-Output ('MB=' + [math]::Round((Get-ChildItem $inst -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB,1))
}
Write-Output ('node=' + (@(Get-Process node -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }) -join ','))
