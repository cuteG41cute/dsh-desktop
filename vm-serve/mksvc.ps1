$ErrorActionPreference = 'Continue'
$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
$dir  = Join-Path $root 'svctest'
if (Test-Path $dir) { Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'node') | Out-Null
Copy-Item (Get-Command node).Source (Join-Path $dir 'node\node.exe') -Force
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'app\apps\cli\src') | Out-Null
Set-Content (Join-Path $dir 'app\apps\cli\src\bin.ts') 'console.log("fake")' -Encoding UTF8
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'dsh-home') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'tools') | Out-Null
$held = Join-Path $dir 'held-open.dat'
Set-Content $held ('x' * 4096) -Encoding ASCII

# 登记为管理器创建的实例
$reg = Join-Path $env:APPDATA 'dsh-manager\instances.json'
$entry = [ordered]@{
    Id = 'svctest'; Label = 'svctest'; Dir = $dir; Port = 3081
    DshVersion = '0.2.2-rc.1'; NodeVersion = '27.0.0-alpha.0'
    CreatedAt = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
}
Set-Content $reg (ConvertTo-Json @($entry) -Depth 5) -Encoding UTF8

# 起一个真的 node 服务占用 3081，并让它一直握着 held-open.dat 的句柄
$js = @'
const http = require("http");
const fs = require("fs");
const fd = fs.openSync(process.argv[1], "r");
http.createServer((q, s) => { s.end("ok"); }).listen(3081, "127.0.0.1");
setInterval(() => { try { fs.readSync(fd, Buffer.alloc(16), 0, 16, 0); } catch (e) {} }, 1000);
'@
$jsPath = Join-Path $env:TEMP 'fake-service.js'
Set-Content $jsPath $js -Encoding UTF8
$node = Join-Path $dir 'node\node.exe'
$p = Start-Process $node -ArgumentList @($jsPath, $held) -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3
Set-Content (Join-Path $env:TEMP 'fake-service.pid') $p.Id -Encoding ASCII

Write-Output ('dir=' + (Test-Path $dir))
Write-Output ('service_pid=' + $p.Id)
Write-Output ('port3081=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
Write-Output ('registry=' + ((Get-Content $reg -Raw) -replace "`r`n", ' '))
