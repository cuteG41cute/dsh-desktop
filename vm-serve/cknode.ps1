$node = 'C:\Users\User\AppData\Local\dsh-manager\instances\dsh-new\node'
Write-Output ('node_exe=' + (Test-Path (Join-Path $node 'node.exe')))
if (Test-Path (Join-Path $node 'node.exe')) { Write-Output ('ver=' + (& (Join-Path $node 'node.exe') --version)) }
Write-Output ('npm=' + (Test-Path (Join-Path $node 'npm.cmd')))
Write-Output ('MB=' + [math]::Round((Get-ChildItem $node -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB,1))
