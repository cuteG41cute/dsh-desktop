<#
  DeepSeek Harness 桌面启动器
  ==========================
  双击 "启动 DeepSeek Harness.cmd" 即会运行本脚本：

    1. 检查 http://127.0.0.1:3080 上的 WebUI 是否已在运行；
       未运行则启动 `dsh web` 服务（后台、无窗口）。
    2. 等待服务就绪（最多 $TimeoutSeconds 秒）。
    3. 用 dsh-desktop\DSH Desktop.exe（WebView2 桌面窗口）打开 WebUI；
       若该包装程序不存在，则回退到 Edge 应用模式窗口，再回退到默认浏览器。
    4. 桌面窗口关闭后，若服务是本脚本启动的，则一并停止服务。
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

# 探测 WebUI：HTTP 200 且页面带有 DeepSeek Harness 的特征标记。
function Test-WebUi {
    param([string]$Uri)
    try {
        $r = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -eq 200 -and $r.Content -match "__DSH_BOOT__")
    } catch {
        return $false
    }
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
    $serverArgs = @("`"$dshBin`"", "web")
    try {
        $uri = [System.Uri]$Url
        if ($uri.Port -gt 0 -and $uri.Port -ne 80) { $serverArgs += @("--port", "$($uri.Port)") }
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
} else {
    Write-Log "服务已在运行，直接打开窗口。"
}

# ---- 3. 打开桌面窗口（阻塞等待窗口关闭） ----
$exe = Join-Path $root "dsh-desktop\DSH Desktop.exe"
$windowProc = $null
$leaveServerRunning = $false
$alreadyRunning = $false

if (Test-Path $exe) {
    Write-Log "打开桌面窗口: $Url"
    $windowProc = Start-Process -FilePath $exe -ArgumentList @($Url) -PassThru
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
            -ArgumentList @("--app=$Url", "--user-data-dir=$profile", "--no-first-run", "--no-default-browser-check") `
            -PassThru
        $windowProc.WaitForExit()
    } else {
        # 最后回退：默认浏览器。无法得知标签页何时关闭，因此保留服务继续运行。
        Write-Log "回退到默认浏览器（服务保持运行，可稍后手动停止）: $Url"
        $leaveServerRunning = $true
        Start-Process $Url
    }
}

# ---- 4. 窗口关闭后清理 ----
if (-not $leaveServerRunning -and -not $alreadyRunning -and $startedByUs -and $proc -and -not $proc.HasExited) {
    Write-Log "桌面窗口已关闭，停止 dsh 服务…"
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
Write-Log "完成。"
