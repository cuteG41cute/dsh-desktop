$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
$dir  = Join-Path $root 'svctest'
$srcNode = Join-Path $root 'dsh-a\node\node.exe'
Write-Output ('src=' + (Test-Path $srcNode))
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'node') | Out-Null
Copy-Item $srcNode (Join-Path $dir 'node\node.exe') -Force
Write-Output ('dst=' + (Test-Path (Join-Path $dir 'node\node.exe')))
$held = Join-Path $dir 'held-open.dat'
Set-Content $held ('x' * 4096) -Encoding ASCII

$jsPath = 'C:\Users\User\fake-service.js'
$js = @'
const http = require("http");
const fs = require("fs");
const fd = fs.openSync(process.argv[2], "r");
http.createServer((q, s) => { s.end("ok"); }).listen(3081, "127.0.0.1");
setInterval(() => { try { fs.readSync(fd, Buffer.alloc(16), 0, 16, 0); } catch (e) {} }, 1000);
'@
Set-Content $jsPath $js -Encoding UTF8

$node = Join-Path $dir 'node\node.exe'
$p = Start-Process -FilePath $node -ArgumentList @($jsPath, $held) -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 4
Write-Output ('pid=' + $(if ($p) { $p.Id } else { 'none' }))
Write-Output ('port=' + (@(Get-NetTCPConnection -LocalPort 3081 -ErrorAction SilentlyContinue).Count))
if ($p) { Set-Content (Join-Path $env:TEMP 'fake-service.pid') $p.Id -Encoding ASCII }
