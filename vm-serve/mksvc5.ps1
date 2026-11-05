$ErrorActionPreference = 'Continue'
$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
$dir  = Join-Path $root 'svctest'
$srcNode = Join-Path $root 'dsh-a\node\node.exe'
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'node') | Out-Null
Copy-Item $srcNode (Join-Path $dir 'node\node.exe') -Force
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'app\apps\cli\src') | Out-Null
Set-Content (Join-Path $dir 'app\apps\cli\src\bin.ts') 'console.log("fake")' -Encoding UTF8
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'dsh-home') | Out-Null
Write-Output ('node=' + (Test-Path (Join-Path $dir 'node\node.exe')))
Write-Output ('fakepage_js=' + (Test-Path 'C:\Users\User\fakepage.js'))

$reg = Join-Path $env:APPDATA 'dsh-manager\instances.json'
$entry = [ordered]@{
    Id = 'svctest'; Label = 'svctest'; Dir = $dir; Port = 3081
    DshVersion = '0.2.2-rc.1'; NodeVersion = '27.0.0-alpha.0'
    CreatedAt = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
}
New-Item -ItemType Directory -Force -Path (Split-Path $reg) | Out-Null
Set-Content $reg (ConvertTo-Json @($entry) -Depth 5) -Encoding UTF8
Write-Output 'registry=ok'
