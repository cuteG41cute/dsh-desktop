<#
  DeepSeek Harness 桌面启动器
  ==========================
  双击 "启动 DeepSeek Harness.vbs" 即会运行本脚本：

    1. 检查 http://127.0.0.1:3080 上的 WebUI 是否已在运行；
       未运行则启动 `dsh web` 服务（后台、无窗口）。
    2. 等待服务就绪（最多 $TimeoutSeconds 秒）。
    3. 取得 Web 认证凭据：dsh ≥0.1.5 的 WebUI 需要一枚签名 cookie 才返回页面
       （未认证时返回 401）。本脚本优先自行签发并用真实请求验证这枚 cookie，
       再交给桌面窗口注入；取不到时才退回「带 token 的认证 URL」方式。
    4. 用 DSH Desktop.exe（WebView2 桌面窗口）打开 WebUI；
       若该包装程序不存在，则回退到 Edge 应用模式窗口，再回退到默认浏览器。
    5. 桌面窗口关闭后，若服务是本脚本启动的，则一并停止服务。

  目录布局（两种都支持，包装程序位置自动识别）：
    · 开发目录 / 免安装目录：launcher.ps1 与 DSH Desktop.exe 同目录（本仓库的 dsh-desktop\）
    · 安装目录：launcher.ps1 在安装根，包装程序在 dsh-desktop\ 子目录
  运行期产物：同目录下的 logs\（服务日志）、edge-profile\（Edge 回退的配置目录）。
#>
[CmdletBinding()]
param(
    [string]$Url = "http://127.0.0.1:3080",
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Write-Log {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message)
}

function Show-Error {
    param([string]$Message)
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    [System.Windows.Forms.MessageBox]::Show($Message, "DeepSeek Harness",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
}

# 探测 WebUI 是否在运行。
# 兼容两种 dsh 形态：
#   旧版（≤0.1.0-rc.x）：根路径直接返回 200 + __DSH_BOOT__
#   新版（≥0.1.5）：引入 Web 认证 —— 未认证访问返回 401（提示 reopen the URL printed by dsh web），
#                   认证后（cookie 有效）返回 200 + __DSH_BOOT__
# 两种情况都说明「服务已在运行」。
function Test-WebUi {
    param([string]$Uri)
    try {
        $r = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -eq 200 -and $r.Content -match "__DSH_BOOT__")
    } catch {
        $resp = $_.Exception.Response
        if ($resp -and [int]$resp.StatusCode -eq 401) {
            try {
                $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
                $body = $reader.ReadToEnd(); $reader.Close()
                # 仅认 dsh 自己的认证响应，避免把其他占用端口的服务误判为 dsh
                return ($body -match "dsh web authentication required")
            } catch { return $false }
        }
        return $false
    }
}

# 从 dsh web 的 stdout 日志中解析「认证 URL」（新版 dsh 启动时打印）：
#   dsh web: http://127.0.0.1:3080/?token=xxxx
# 用它打开窗口可自动完成认证并种下 30 天有效的签名 cookie。
function Get-AuthenticatedUrl {
    param([string]$LogPath)
    if (-not $LogPath -or -not (Test-Path $LogPath)) { return $null }
    try {
        $text = Get-Content $LogPath -Raw -ErrorAction SilentlyContinue
        if (-not $text) { return $null }
        $m = [regex]::Match($text, 'dsh web: (http://\S+)')
        if ($m.Success) { return $m.Groups[1].Value.Trim() }
    } catch { }
    return $null
}

# ---- dsh ≥0.1.5 的 Web 认证：自行签发并验证会话 cookie ----
# dsh 让浏览器用「每个进程随机的一次性 token」换取一枚长期签名 cookie。token 只在
# 服务进程内，外部推导不出来；但签名密钥是持久的（每个 Harness home 一份，存在
# $DSH_HOME\.credentials.yaml 的 client-connection/browser-session 记录里），cookie
# 的格式也是确定的：
#   cookie 名 = "dsh-auth-" + base64url(sha256(authority))
#   cookie 值 = "v1." + base64url(payload) + "." + base64url(HMAC-SHA256(secret, payload))
#   payload   = {"version":1,"authority":"host:port","issuedAt":ms,"expiresAt":ms}
# 所以本脚本可以自己签发一枚 cookie，并用一次真实 HTTP 请求确认它真的被服务接受。
# 这样即使 WebUI 是用户在别处手动启动的（读不到 token 日志），窗口也能正常认证。
# 若将来 dsh 改了密钥存放或 cookie 格式，验证会失败，脚本自动退回认证 URL 方式。
function Get-DshHomePath {
    if ($env:DSH_HOME) { return $env:DSH_HOME }
    return (Join-Path $HOME ".dsh")
}

function Get-DshAuthSecret {
    try {
        $file = Join-Path (Get-DshHomePath) ".credentials.yaml"
        if (-not (Test-Path $file)) { return $null }
        $text = Get-Content $file -Raw -ErrorAction SilentlyContinue
        if (-not $text) { return $null }
        $m = [regex]::Match($text, '(?s)client-connection/browser-session:.*?secret:\s*([A-Za-z0-9_\-]+)')
        if ($m.Success) { return $m.Groups[1].Value }
    } catch { }
    return $null
}

function ConvertTo-Base64Url {
    param([byte[]]$Bytes)
    return ([Convert]::ToBase64String($Bytes)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function ConvertFrom-Base64Url {
    param([string]$Text)
    $padded = $Text.Replace('-', '+').Replace('_', '/')
    while ($padded.Length % 4) { $padded += '=' }
    return [Convert]::FromBase64String($padded)
}

# 为来源（host:port）签发一枚有效期 $Days 天的会话 cookie。
function New-DshAuthCookie {
    param([string]$Authority, [string]$Secret, [int]$Days = 30)
    $secretBytes = ConvertFrom-Base64Url $Secret
    if ($secretBytes.Length -ne 32) { throw "意外的签名密钥长度: $($secretBytes.Length)" }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $name = "dsh-auth-" + (ConvertTo-Base64Url ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Authority))))
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $expires = $now + ([int64]$Days * 24 * 3600 * 1000)
    $json = '{"version":1,"authority":"' + $Authority + '","issuedAt":' + $now + ',"expiresAt":' + $expires + '}'
    $body = ConvertTo-Base64Url ([Text.Encoding]::UTF8.GetBytes($json))
    $hmac = New-Object System.Security.Cryptography.HMACSHA256
    $hmac.Key = $secretBytes
    $signature = ConvertTo-Base64Url ($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($body)))
    return [pscustomobject]@{ Name = $name; Value = "v1.$body.$signature"; Days = $Days }
}

# 用真实请求验证 cookie：拿到 200 + __DSH_BOOT__ 才算有效。
# 注意：不能用 Invoke-WebRequest -Headers @{Cookie=...}——PowerShell 5.1 会丢弃这个受限头。
function Test-DshAuthCookie {
    param([string]$Uri, [string]$Name, [string]$Value)
    $req = $null
    try {
        $target = [System.Uri]$Uri
        $req = [System.Net.HttpWebRequest]::Create($target)
        $req.Method = "GET"
        $req.Timeout = 5000
        $req.AllowAutoRedirect = $false
        $req.CookieContainer = New-Object System.Net.CookieContainer
        $req.CookieContainer.Add((New-Object System.Net.Cookie($Name, $Value, "/", $target.Host)))
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $body = $reader.ReadToEnd()
        $reader.Close()
        $resp.Close()
        return ($code -eq 200 -and $body -match "__DSH_BOOT__")
    } catch {
        return $false
    } finally {
        if ($req) { try { $req.Abort() } catch { } }
    }
}

# 解析当前来源可用的「已验证」会话 cookie（失败返回 $null）。
# cookie 有效期必须不大于服务端配置（默认 cookieMaxAgeDays = 30），因此按 30/7/1 天依次尝试。
function Resolve-DshAuthCookie {
    param([string]$Uri)
    try { $authority = ([System.Uri]$Uri).Authority } catch { return $null }
    if (-not $authority) { return $null }
    $secret = Get-DshAuthSecret
    if (-not $secret) { return $null }
    foreach ($days in @(30, 7, 1)) {
        $cookie = $null
        try { $cookie = New-DshAuthCookie -Authority $authority -Secret $secret -Days $days } catch { return $null }
        if (Test-DshAuthCookie -Uri $Uri -Name $cookie.Name -Value $cookie.Value) { return $cookie }
    }
    return $null
}

# ---- 1. 定位 dsh CLI（node + bin.js） ----
function Find-Node {
    # PATH 上的 node
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) { return $cmd.Source }
    # 常见安装位置（含 nvm-windows）
    $candidates = @(
        (Join-Path $env:ProgramFiles "nodejs\node.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "nodejs\node.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\nodejs\node.exe"),
        (Join-Path $env:APPDATA "nvm\node.exe")
    )
    foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { return $c } }
    $nvmRoot = Join-Path $env:APPDATA "nvm"
    if (Test-Path $nvmRoot) {
        $n = Get-ChildItem -Path $nvmRoot -Recurse -Filter "node.exe" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($n) { return $n.FullName }
    }
    return $null
}

function Find-DshBin {
    # 0) 优先读取同目录 dsh-path.config（安装程序写入的指定路径）
    $configPath = Join-Path $PSScriptRoot "dsh-path.config"
    if (Test-Path $configPath) {
        $configured = ((Get-Content $configPath -Raw -ErrorAction SilentlyContinue) -split "`r?`n")[0].Trim()
        if ($configured) {
            if (Test-Path $configured) {
                return $configured
            }
            Write-Log "警告: dsh-path.config 指向的路径不存在（$configured），将自动扫描其他位置。"
        }
    }
    # 1) npx 缓存里的真实 bin.js（递归查找，取最新的安装）
    $npxRoot = Join-Path $env:LOCALAPPDATA "npm-cache\_npx"
    if (Test-Path $npxRoot) {
        $found = Get-ChildItem -Path (Join-Path $npxRoot "*") -Recurse -Filter "bin.js" `
            -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like "*@deepseek-ai\dsh\lib\bin.js" } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    # 2) 全局 npm 安装位置
    $globalCandidates = @(
        (Join-Path $env:APPDATA "npm\node_modules\@deepseek-ai\dsh\lib\bin.js"),
        (Join-Path $env:ProgramFiles "nodejs\node_modules\@deepseek-ai\dsh\lib\bin.js"),
        (Join-Path ${env:ProgramFiles(x86)} "nodejs\node_modules\@deepseek-ai\dsh\lib\bin.js"),
        (Join-Path $env:LOCALAPPDATA "Programs\nodejs\node_modules\@deepseek-ai\dsh\lib\bin.js")
    )
    foreach ($c in $globalCandidates) { if ($c -and (Test-Path $c)) { return $c } }
    # 3) $DSH_HOME profiles 里随 profile 安装的 dsh
    $dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $HOME ".dsh" }
    $profilesBin = Join-Path $dshHome "profiles\node_modules\@deepseek-ai\dsh\lib\bin.js"
    if (Test-Path $profilesBin) { return $profilesBin }
    # 4) 兜底：PATH 上的 dsh shim（.bin 与包目录是同级的，可以直接推导出 bin.js）
    $cmd = Get-Command dsh -ErrorAction SilentlyContinue
    if ($cmd) {
        $src = $cmd.Source
        $derived = $src -replace '\\node_modules\\\.bin\\dsh\.(ps1|cmd)$', '\node_modules\@deepseek-ai\dsh\lib\bin.js'
        if (Test-Path $derived) { return $derived }
        return $src
    }
    return $null
}

$node = Find-Node
$dshBin = Find-DshBin
if (-not $dshBin) {
    Show-Error "找不到 dsh 命令行程序。`n`n请先运行：`n  npm install -g @deepseek-ai/dsh`n或通过 npx 启动过一次 DeepSeek Harness。`n也可以使用「安装 DeepSeek Harness 桌面版」安装程序来自动检测或安装。"
    exit 1
}
if (-not $node) {
    Show-Error "找不到 node.exe，无法启动 dsh 服务。请安装 Node.js（https://nodejs.org）后重试。"
    exit 1
}
Write-Log ("使用 node: {0}" -f $node)
Write-Log ("使用 dsh: {0}" -f $dshBin)

# ---- 2. 确保 WebUI 服务在运行 ----
$startedByUs = $false
$proc = $null
$running = Test-WebUi -Uri $Url
$authUrl = $null

if (-not $running) {
    $logDir = Join-Path $root "logs"
    New-Item -ItemType Directory -Force $logDir | Out-Null
    $outLog = Join-Path $logDir "server.out.log"
    $errLog = Join-Path $logDir "server.err.log"

    Write-Log "启动 dsh web 服务（$Url）…"
    if (-not $node) {
        Show-Error "找不到 node.exe，无法启动 dsh 服务。"
        exit 1
    }
    # 服务端口跟随 $Url（默认 3080），保证探测的地址就是服务监听的地址。
    # --no-open：新版 dsh web 默认会打开系统浏览器（认证 URL），桌面版自己开窗，必须禁用。
    $serverArgs = @("`"$dshBin`"", "web", "--no-open")
    try {
        $uri = [System.Uri]$Url
        if ($uri.Port -gt 0 -and $uri.Port -ne 80) { $serverArgs += @("--port", "$($uri.Port)") }
        # 手机/平板局域网接入（dsh-mobile-bridge）：把手机侧看到的来源登记进 /api 的 Host/Origin 信任栅栏。
        # 每个网卡 IP + 桥端口；桥端口可用 $env:DSH_BRIDGE_PORT 覆盖（默认 8099）。
        $bridgePort = if ($env:DSH_BRIDGE_PORT) { [int]$env:DSH_BRIDGE_PORT } else { 8099 }
        foreach ($addr in [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName())) {
            if ($addr.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and -not [System.Net.IPAddress]::IsLoopback($addr)) {
                $serverArgs += @("--trusted-host", ("{0}:{1}" -f $addr.IPAddressToString, $bridgePort))
            }
        }
    } catch { }
    $proc = Start-Process -FilePath $node `
        -ArgumentList $serverArgs `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-WebUi -Uri $Url) { $running = $true; break }
        if ($proc.HasExited) { break }
        Start-Sleep -Milliseconds 1500
    }

    if (-not $running) {
        $detail = ""
        if (Test-Path $errLog) {
            $tail = Get-Content $errLog -Tail 40 -ErrorAction SilentlyContinue
            if ($tail) { $detail = ($tail -join "`n") }
        }
        if (-not $detail) { $detail = "服务进程已退出（退出码: $($proc.ExitCode)）。" }
        Show-Error "DeepSeek Harness WebUI 未能启动。`n`n$detail"
        if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
        exit 1
    }
    $startedByUs = $true
    Write-Log "服务已就绪。"

    # 新版 dsh 的 Web 认证：从启动日志解析认证 URL（含进程级 token）
    $authUrl = Get-AuthenticatedUrl -LogPath $outLog
} else {
    Write-Log "服务已在运行，直接打开窗口。"
    # 服务是外部启动的：尝试从本启动器此前的日志里取认证 URL（cookie 通常仍然有效）
    $prevLog = Join-Path $root "logs\server.out.log"
    $authUrl = Get-AuthenticatedUrl -LogPath $prevLog
}

# ---- 3. 打开桌面窗口（阻塞等待窗口关闭） ----
# 包装程序位置：开发/免安装目录里与启动器同目录；安装目录里在 dsh-desktop\ 子目录。
$exe = Join-Path $root "DSH Desktop.exe"
if (-not (Test-Path $exe)) {
    $nestedExe = Join-Path $root "dsh-desktop\DSH Desktop.exe"
    if (Test-Path $nestedExe) { $exe = $nestedExe }
}
$windowProc = $null
$leaveServerRunning = $false
$alreadyRunning = $false

# 认证凭据优先级：
#   1) 自行签发并用真实请求验证过的会话 cookie（不依赖日志，服务是外部启动的也能用）
#      —— 通过环境变量交给桌面窗口，由窗口注入 WebView2 配置，窗口用干净的地址打开；
#   2) `dsh web` 打印的带 token 认证 URL（读完 cookie 后官网路径，退回时使用）；
#   3) 都没有：照旧打开原地址（若配置里已有有效 cookie 仍可正常显示）。
$windowUrl = $Url
$browserUrl = $Url
$authCookie = Resolve-DshAuthCookie -Uri $Url
if ($authCookie) {
    $env:DSH_DESKTOP_AUTH_COOKIE = "$($authCookie.Name)=$($authCookie.Value)"
    $env:DSH_DESKTOP_AUTH_COOKIE_MAXAGE = "$([int]($authCookie.Days) * 86400)"
    Write-Log "已签发并验证 Web 认证 cookie（有效期 $($authCookie.Days) 天），窗口将直接认证。"
} elseif ($authUrl) {
    $windowUrl = $authUrl
    $browserUrl = $authUrl
    Write-Log "已获取认证 URL，窗口将自动完成 Web 认证。"
} else {
    Write-Log "未取得认证凭据；若窗口显示认证提示，请用 dsh web 打印的带 token 地址打开一次。"
}

# 桌面窗口优先走本机桥（dsh-mobile-bridge, 默认 8099）：
#   「设置 → 手机端」（二维码 + 设备管理）是桥注入的客户端插件，直连 3080 的窗口看不到它；
#   桥自己会给页面签发认证 cookie，所以走桥时不需要上面的凭据。
#   桥没在跑就照旧直连，窗口一定能打开（桥是可选增强，不是硬依赖）。
#   但桥要往 __DSH_BOOT__ 里插条目 —— DSH 换版本若改了清单结构，插错一步就是白屏，
#   而白屏的恰好是这个窗口（唯一还能改设置的地方）。所以先让桥自检：/__selftest 会
#   真的向上游取一次首页、把注入管线完整跑一遍。自检不过就退回官方端口，窗口一定开得出来
#   （代价只是没有「手机端」面板，手机侧功能不受影响）。
#   想强制直连：设环境变量 DSH_DESKTOP_DIRECT=1。
$bridgeBase = "http://127.0.0.1:8099/"
$bridgeUsable = $false
if ($env:DSH_DESKTOP_DIRECT -eq "1") {
    Write-Log "按 DSH_DESKTOP_DIRECT=1 强制直连官方端口（不会有「手机端」面板）。"
} else {
    try {
        $probe = Invoke-WebRequest -Uri ($bridgeBase + "__selftest") -UseBasicParsing -TimeoutSec 8
        if ($probe.StatusCode -eq 200) {
            $self = $probe.Content | ConvertFrom-Json
            $bridgeUsable = [bool]$self.ok
            if ($bridgeUsable) {
                Write-Log "桥自检通过：面板注入=$($self.panel) 移动端适配=$($self.tweaks) 按设备隔离=$($self.describe) — $($self.note)"
            } else {
                Write-Log "桥自检未通过（$($self.note)）→ 桌面窗口直连官方端口，避免白屏；手机侧不受影响。"
            }
        }
    } catch {
        $bridgeUsable = $false
    }
}
if ($bridgeUsable) {
    $windowUrl = $bridgeBase
    $browserUrl = $bridgeBase
    Write-Log "桌面窗口走本机桥: $bridgeBase （设置里会有「手机端」面板）"
}

if (Test-Path $exe) {
    Write-Log "打开桌面窗口: $windowUrl"
    $windowProc = Start-Process -FilePath $exe -ArgumentList @($windowUrl) -PassThru
    $windowProc.WaitForExit()
    # 退出码 42 = 程序已在运行（单实例短路，旧窗口已被唤起），不代表关闭了窗口。
    try { if ($windowProc.ExitCode -eq 42) { $alreadyRunning = $true } } catch { }
    if ($alreadyRunning) {
        Write-Log "桌面窗口已在运行（本次仅唤起现有窗口），不会停止服务。"
    }
} else {
    # 回退 1：Edge / Chrome 应用模式（独立无边框窗口，不显示浏览器界面）
    $edgeCandidates = @(
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    )
    $browser = $edgeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($browser) {
        Write-Log "未找到桌面包装程序，回退到应用模式: $browser"
        $profile = Join-Path $root "edge-profile"
        $windowProc = Start-Process -FilePath $browser `
            -ArgumentList @("--app=$browserUrl", "--user-data-dir=$profile", "--no-first-run", "--no-default-browser-check") `
            -PassThru
        $windowProc.WaitForExit()
    } else {
        # 最后回退：默认浏览器。无法得知标签页何时关闭，因此保留服务继续运行。
        Write-Log "回退到默认浏览器（服务保持运行，可稍后手动停止）: $browserUrl"
        $leaveServerRunning = $true
        Start-Process $browserUrl
    }
}

# ---- 4. 窗口关闭后清理 ----
if (-not $leaveServerRunning -and -not $alreadyRunning -and $startedByUs -and $proc -and -not $proc.HasExited) {
    Write-Log "桌面窗口已关闭，停止 dsh 服务…"
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
Write-Log "完成。"
