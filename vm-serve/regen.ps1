$root = 'C:\Users\User\AppData\Local\dsh-manager\instances\svctest'
$node = Join-Path $root 'node\node.exe'
Write-Output ('node=' + (Test-Path $node))
$reg = Join-Path $env:APPDATA 'dsh-manager\instances.json'
$entry = [ordered]@{
    Id = 'svctest'; Label = 'svctest'; Dir = $root; Port = 3081
    DshVersion = '0.2.2-rc.1'; NodeVersion = '27.0.0-alpha.0'
    CreatedAt = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
}
Set-Content $reg (ConvertTo-Json @($entry) -Depth 5) -Encoding UTF8
Write-Output 'registry written'
