$inst = 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new'
Write-Output ('dir=' + (Test-Path $inst))
if (Test-Path $inst) {
  $kids = @(Get-ChildItem $inst -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
  Write-Output ('kids=' + ($kids -join ','))
  Write-Output ('MB=' + [math]::Round((Get-ChildItem $inst -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB,1))
}
Write-Output ('list=' + (@(Get-ChildItem 'C:\Users\User\AppData\Local\dsh-manager\instances' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ','))
Write-Output ('node=' + (@(Get-Process node -ErrorAction SilentlyContinue).Count))
