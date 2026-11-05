$ErrorActionPreference = 'Continue'
$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
$dir  = Join-Path $root 'faketest'
if (Test-Path $dir) { Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $dir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'node') | Out-Null
Copy-Item (Get-Command node).Source (Join-Path $dir 'node\node.exe') -Force
$app = Join-Path $dir 'app'
New-Item -ItemType Directory -Force -Path (Join-Path $app 'apps\cli\src') | Out-Null
Set-Content (Join-Path $app 'apps\cli\src\bin.ts') 'console.log("fake")' -Encoding UTF8
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'dsh-home') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'pnpm-store\v10\files\aa') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'tools\node_modules\pnpm\bin') | Out-Null
# 制造只读文件 + 深路径，模拟真实 node_modules / pnpm-store
1..40 | ForEach-Object {
    $p = Join-Path $dir ("pnpm-store\v10\files\aa\{0:x2}-deep-file.txt" -f $_)
    Set-Content $p ('x' * 200) -Encoding ASCII
    (Get-Item $p).IsReadOnly = $true
}
$deep = Join-Path $dir 'tools\node_modules\pnpm\bin\pnpm.cjs'
Set-Content $deep '// pnpm stub' -Encoding UTF8
(Get-Item $deep).IsReadOnly = $true

$reg = Join-Path $env:APPDATA 'dsh-manager\instances.json'
New-Item -ItemType Directory -Force -Path (Split-Path $reg) | Out-Null
$entry = [ordered]@{
    Id = 'faketest'
    Label = 'faketest'
    Dir = $dir
    Port = 3099
    DshVersion = '0.2.2-rc.1'
    NodeVersion = '27.0.0-alpha.0'
    CreatedAt = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
}
Set-Content $reg (ConvertTo-Json @($entry) -Depth 5) -Encoding UTF8

$files = @(Get-ChildItem $dir -Recurse -File -Force -ErrorAction SilentlyContinue)
$ro = @($files | Where-Object { $_.IsReadOnly })
Write-Output ('created=' + (Test-Path $dir))
Write-Output ('files=' + $files.Count)
Write-Output ('readonly=' + $ro.Count)
Write-Output ('registry=' + (Get-Content $reg -Raw))
