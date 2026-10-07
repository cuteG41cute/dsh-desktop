<#
  安装 DeepSeek Harness 桌面版（自适应安装程序）
  =============================================
  双击「安装 DeepSeek Harness 桌面版.vbs」运行本脚本（无控制台窗口）。

  流程：
    1. 扫描本机已安装的 DeepSeek Harness（npx 缓存 / 全局 npm / $DSH_HOME profiles / PATH）。
    2. 找到 → 直接进入安装。
    3. 未找到 → 询问用户：
       a. 「请帮助我安装好 DeepSeek Harness」
          → 检测 Node.js → npm install -g @deepseek-ai/dsh → 重新扫描；
       b. 手动输入 DeepSeek Harness 的安装路径
          → 验证该路径下是否存在 dsh 程序：
             - 不存在 → 提醒用户，可「重新输入 / 仍然安装（执意）/ 取消」；
             - 存在   → 使用该路径。
    4. 安装桌面版皮肤到 %LOCALAPPDATA%\Programs\DSH Desktop\
       （复制启动器、WebView2 桌面程序、入口 vbs；创建桌面与开始菜单快捷方式；
       手动指定路径时写入 dsh-path.config，启动器优先使用该路径）。
    5. 「执意安装」（提供路径下没有 dsh）时，安装完成后再次警告：
       桌面版可能无法正常使用，并告知卸载程序的路径。

  测试模式（无任何对话框，结果写入 %TEMP%\dsh-installer.log）：
    -SilentInstall [-DshPath <path>]   直接安装；省略 DshPath 时自动扫描
    -SilentUninstall                   直接卸载（要求已安装）
#>
[CmdletBinding()]
param(
    [switch]$SilentInstall,
    [switch]$SilentUninstall,
    [string]$DshPath = ""
)

$ErrorActionPreference = "Stop"
$sourceRoot = $PSScriptRoot
$installDir = Join-Path $env:LOCALAPPDATA "Programs\DSH Desktop"
$installerLog = Join-Path $env:TEMP "dsh-installer.log"
$silent = $SilentInstall -or $SilentUninstall

Add-Type -AssemblyName System.Windows.Forms | Out-Null
Add-Type -AssemblyName Microsoft.VisualBasic | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    if ($silent) {
        Add-Content -Path $installerLog -Value $line -Encoding UTF8
    } else {
        Write-Host $line
    }
}

function Show-Info {
    param([string]$Message, [string]$Title = "DeepSeek Harness 桌面版安装")
    if ($silent) { Write-Log "INFO: $Message"; return [System.Windows.Forms.DialogResult]::OK }
    return [System.Windows.Forms.MessageBox]::Show($Message, $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
}

function Show-Error {
    param([string]$Message, [string]$Title = "DeepSeek Harness 桌面版安装")
    if ($silent) { Write-Log "ERROR: $Message"; return [System.Windows.Forms.DialogResult]::OK }
    return [System.Windows.Forms.MessageBox]::Show($Message, $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
}

function Show-Question {
    param([string]$Message, [string]$Title = "DeepSeek Harness 桌面版安装", [System.Windows.Forms.MessageBoxButtons]$Buttons = [System.Windows.Forms.MessageBoxButtons]::YesNoCancel)
    if ($silent) { Write-Log "QUESTION(auto-OK): $Message"; return [System.Windows.Forms.DialogResult]::OK }
    return [System.Windows.Forms.MessageBox]::Show($Message, $Title, $Buttons, [System.Windows.Forms.MessageBoxIcon]::Question)
}

function Show-InputBox {
    param([string]$Prompt, [string]$Title = "输入路径", [string]$Default = "")
    if ($silent) { return "" }
    return [Microsoft.VisualBasic.Interaction]::InputBox($Prompt, $Title, $Default)
}

# ---- 扫描已安装的 DeepSeek Harness ----
function Find-Node {
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:ProgramFiles "nodejs\node.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "nodejs\node.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\nodejs\node.exe")
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

function Find-Npm {
    $cmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:APPDATA "npm\npm.cmd"),
        (Join-Path $env:ProgramFiles "nodejs\npm.cmd"),
        (Join-Path $env:LOCALAPPDATA "Programs\nodejs\npm.cmd")
    )
    foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { return $c } }
    return $null
}

function Find-DshBin {
    $npxRoot = Join-Path $env:LOCALAPPDATA "npm-cache\_npx"
    if (Test-Path $npxRoot) {
        $found = Get-ChildItem -Path (Join-Path $npxRoot "*") -Recurse -Filter "bin.js" `
            -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like "*@deepseek-ai\dsh\lib\bin.js" } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    $globalCandidates = @(
        (Join-Path $env:APPDATA "npm\node_modules\@deepseek-ai\dsh\lib\bin.js"),
        (Join-Path $env:ProgramFiles "nodejs\node_modules\@deepseek-ai\dsh\lib\bin.js"),
        (Join-Path ${env:ProgramFiles(x86)} "nodejs\node_modules\@deepseek-ai\dsh\lib\bin.js"),
        (Join-Path $env:LOCALAPPDATA "Programs\nodejs\node_modules\@deepseek-ai\dsh\lib\bin.js")
    )
    foreach ($c in $globalCandidates) { if ($c -and (Test-Path $c)) { return $c } }
    $dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $HOME ".dsh" }
    $profilesBin = Join-Path $dshHome "profiles\node_modules\@deepseek-ai\dsh\lib\bin.js"
    if (Test-Path $profilesBin) { return $profilesBin }
    $cmd = Get-Command dsh -ErrorAction SilentlyContinue
    if ($cmd) {
        $src = $cmd.Source
        $derived = $src -replace '\\node_modules\\\.bin\\dsh\.(ps1|cmd)$', '\node_modules\@deepseek-ai\dsh\lib\bin.js'
        if (Test-Path $derived) { return $derived }
        return $src
    }
    return $null
}

# ---- 验证用户输入的路径是否能解析为 dsh 程序（bin.js） ----
function Resolve-DshPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    $Path = $Path.Trim().Trim('"')
    if (-not (Test-Path $Path)) { return $null }
    $item = Get-Item $Path -ErrorAction SilentlyContinue
    if (-not $item) { return $null }

    if (-not $item.PSIsContainer) {
        # 直接指向 bin.js
        if ($item.Name -eq "bin.js") { return $item.FullName }
        # 指向 node.exe → 找同级的 node_modules
        if ($item.Name -eq "node.exe") {
            $cand = Join-Path $item.DirectoryName "node_modules\@deepseek-ai\dsh\lib\bin.js"
            if (Test-Path $cand) { return $cand }
        }
        return $null
    }

    # 目录：依次尝试几种常见布局
    $candidates = @(
        (Join-Path $item.FullName "lib\bin.js"),                                    # @deepseek-ai/dsh 包根
        (Join-Path $item.FullName "node_modules\@deepseek-ai\dsh\lib\bin.js"),      # 项目/全局 node_modules 上层
        (Join-Path $item.FullName "@deepseek-ai\dsh\lib\bin.js"),                   # node_modules 目录本身
        (Join-Path $item.FullName "dsh\lib\bin.js")                                 # @deepseek-ai 作用域目录本身
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

# ---- 帮助安装 DeepSeek Harness（npm 全局安装） ----
function Invoke-HelpInstall {
    $node = Find-Node
    if (-not $node) {
        $r = Show-Question "未检测到 Node.js。安装 DeepSeek Harness 需要 Node.js（npm 随 Node.js 一起安装）。`n`n是否打开 Node.js 官方下载页面？"
        if ($r -eq [System.Windows.Forms.DialogResult]::Yes) { Start-Process "https://nodejs.org" }
        return $null
    }
    $npm = Find-Npm
    if (-not $npm) {
        Show-Error "找到了 Node.js，但未找到 npm。请检查 Node.js 安装是否完整，或手动安装：`n  npm install -g @deepseek-ai/dsh"
        return $null
    }
    Show-Info "正在使用 npm 全局安装 DeepSeek Harness...`n`n这可能需要几分钟，请稍候。"
    Write-Log "npm install -g @deepseek-ai/dsh ..."
    $npmLog = Join-Path $env:TEMP "dsh-npm-install.log"
    try {
        & $npm install -g @deepseek-ai/dsh *> $npmLog
        $code = $LASTEXITCODE
    } catch {
        $code = 1
        Add-Content -Path $npmLog -Value ("EXCEPTION: " + $_.Exception.Message) -Encoding UTF8
    }
    if ($code -ne 0) {
        $tail = (Get-Content $npmLog -Tail 15 -ErrorAction SilentlyContinue) -join "`n"
        Show-Error "npm 安装失败（退出码 $code）。`n`n日志末尾：`n$tail"
        return $null
    }
    Write-Log "npm install 完成。"
    return (Find-DshBin)
}

# ---- 安装桌面版皮肤 ----
function Install-DesktopApp {
    param([string]$DshBinPath)   # 可为 $null（自动扫描）或具体路径（写 config）

    Write-Log "安装目录: $installDir"
    New-Item -ItemType Directory -Force $installDir | Out-Null

    # 1) 复制启动器与入口
    Copy-Item -Path (Join-Path $sourceRoot "launcher.ps1") -Destination $installDir -Force
    Copy-Item -Path (Join-Path $sourceRoot "启动 DeepSeek Harness.vbs") -Destination $installDir -Force
    Copy-Item -Path (Join-Path $sourceRoot "Start DeepSeek Harness.vbs") -Destination $installDir -Force
    Copy-Item -Path (Join-Path $sourceRoot "splash.ps1") -Destination $installDir -Force

    # 2) 复制 WebView2 桌面程序（安装到 dsh-desktop\ 子目录，与 MSI 安装布局一致）
    #    来源：开发/免安装目录里包装程序与启动器同目录；若存在旧的分层结构则取其子目录。
    $srcDesktop = $sourceRoot
    if (Test-Path (Join-Path $sourceRoot "dsh-desktop\DSH Desktop.exe")) {
        $srcDesktop = Join-Path $sourceRoot "dsh-desktop"
    }
    if (Test-Path (Join-Path $srcDesktop "DSH Desktop.exe")) {
        $dstDesktop = Join-Path $installDir "dsh-desktop"
        New-Item -ItemType Directory -Force $dstDesktop | Out-Null
        # 清理历史残留（*.old.exe 等），避免旧版本文件混入
        Get-ChildItem $dstDesktop -Filter "*.old.exe" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
        # 明确清单：开发目录里同目录还有启动器/文档/构建产物，不能整目录复制
        $payload = @(
            "DSH Desktop.exe", "DSH Desktop.exe.config", "App.cs",
            "app.ico", "app.manifest", "icon-source.png",
            "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.Core.xml",
            "Microsoft.Web.WebView2.WinForms.dll", "Microsoft.Web.WebView2.WinForms.xml",
            "WebView2Loader.dll"
        )
        foreach ($name in $payload) {
            $src = Join-Path $srcDesktop $name
            if (Test-Path $src) { Copy-Item $src -Destination $dstDesktop -Force }
        }
    } else {
        Write-Log "警告: 安装包中缺少 DSH Desktop.exe（包装程序）"
    }

    # 3) 手动指定路径时写入 dsh-path.config（启动器优先使用）
    $configPath = Join-Path $installDir "dsh-path.config"
    Remove-Item $configPath -Force -ErrorAction SilentlyContinue
    if ($DshBinPath) {
        Set-Content -Path $configPath -Value $DshBinPath -Encoding ASCII
        Write-Log "已写入 dsh-path.config: $DshBinPath"
    }

    # 4) 写入卸载程序
    $uninstallPs1 = @'
# 卸载 DeepSeek Harness 桌面版
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$installDir = $PSScriptRoot
Add-Type -AssemblyName System.Windows.Forms | Out-Null
function Show-Info {
    param([string]$Message)
    return [System.Windows.Forms.MessageBox]::Show($Message, "DeepSeek Harness 桌面版卸载",
        [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
}
function Show-Confirm {
    param([string]$Message)
    return [System.Windows.Forms.MessageBox]::Show($Message, "DeepSeek Harness 桌面版卸载",
        [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Question)
}
$desktopLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "DeepSeek Harness.lnk"
$startLnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\DeepSeek Harness.lnk"
$r = Show-Confirm ("确定要卸载 DeepSeek Harness 桌面版吗？`n`n将删除：`n  " + $installDir + "`n  桌面快捷方式`n  开始菜单快捷方式`n`n（不会删除 DeepSeek Harness 服务本身及其数据）")
if ($r -ne [System.Windows.Forms.DialogResult]::Yes) { exit 0 }
foreach ($lnk in @($desktopLnk, $startLnk)) {
    if (Test-Path $lnk) { Remove-Item $lnk -Force }
}
if (Test-Path $installDir) {
    Remove-Item $installDir -Recurse -Force
}
Show-Info ("DeepSeek Harness 桌面版已卸载。`n`n如需重新安装，请运行原安装包中的「安装 DeepSeek Harness 桌面版.vbs」。")
'@
    $uninstallPs1 | Out-File -FilePath (Join-Path $installDir "uninstall.ps1") -Encoding UTF8

    $uninstallVbs = @'
' 卸载 DeepSeek Harness 桌面版（无控制台入口）
Option Explicit
Dim fso, shell, dir, cmdLine
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
cmdLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & dir & "\uninstall.ps1"""
shell.Run cmdLine, 0, False
'@
    $uninstallVbs | Out-File -FilePath (Join-Path $installDir "卸载 DeepSeek Harness 桌面版.vbs") -Encoding ASCII

    # 5) 创建快捷方式
    $ws = New-Object -ComObject WScript.Shell
    $iconExe = Join-Path $installDir "dsh-desktop\DSH Desktop.exe"
    $targetVbs = Join-Path $installDir "启动 DeepSeek Harness.vbs"
    $desktopLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "DeepSeek Harness.lnk"
    $startLnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\DeepSeek Harness.lnk"
    foreach ($lnkPath in @($desktopLnk, $startLnk)) {
        $lnk = $ws.CreateShortcut($lnkPath)
        $lnk.TargetPath = $targetVbs
        $lnk.WorkingDirectory = $installDir
        if (Test-Path $iconExe) { $lnk.IconLocation = "$iconExe,0" }
        $lnk.Description = "DeepSeek Harness - desktop launcher"
        $lnk.Save()
        Write-Log "快捷方式: $lnkPath"
    }
}

# ---- 卸载 ----
function Uninstall-DesktopApp {
    if (-not (Test-Path $installDir)) {
        Show-Error "未找到已安装的 DeepSeek Harness 桌面版（$installDir）。"
        return $false
    }
    if (-not $silent) {
        $r = Show-Question ("确定要卸载 DeepSeek Harness 桌面版吗？`n`n将删除：`n  " + $installDir + "`n  桌面快捷方式`n  开始菜单快捷方式`n`n（不会删除 DeepSeek Harness 服务本身及其数据）", "卸载确认", [System.Windows.Forms.MessageBoxButtons]::YesNo)
        if ($r -ne [System.Windows.Forms.DialogResult]::Yes) { return $false }
    }
    foreach ($lnk in @(
        (Join-Path ([Environment]::GetFolderPath("Desktop")) "DeepSeek Harness.lnk"),
        (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\DeepSeek Harness.lnk"))) {
        if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Log "已删除: $lnk" }
    }
    Remove-Item $installDir -Recurse -Force
    Write-Log "已删除: $installDir"
    if ($silent) { return $true }
    Show-Info "DeepSeek Harness 桌面版已卸载。`n`n如需重新安装，请运行原安装包中的「安装 DeepSeek Harness 桌面版.vbs」。"
    return $true
}

# ================= 主流程 =================
Write-Log "=== DeepSeek Harness 桌面版安装程序 ==="

if ($SilentUninstall) {
    $ok = Uninstall-DesktopApp
    Write-Log "卸载结果: $ok"
    exit $(if ($ok) { 0 } else { 1 })
}

# --- 阶段 1：扫描已安装的 DeepSeek Harness ---
$scannedBin = Find-DshBin
$userDshPath = $null        # 手动指定（写 config）
$insisted = $false          # 执意安装标记

if ($SilentInstall) {
    if ($DshPath) {
        $userDshPath = Resolve-DshPath $DshPath
        if (-not $userDshPath) {
            Write-Log "警告: 指定的路径下未发现 dsh 程序（$DshPath），按执意安装处理。"
            $insisted = $true
            $userDshPath = $DshPath   # 仍写入 config（启动器会自动回退扫描）
        } else {
            Write-Log "手动路径有效: $userDshPath"
        }
    } else {
        if ($scannedBin) { Write-Log "自动检测到 dsh: $scannedBin" }
        else { Write-Log "自动检测未发现 dsh（桌面版可安装，启动时将由启动器自动扫描）" }
    }
} else {
    if ($scannedBin) {
        Show-Info "已检测到本机安装的 DeepSeek Harness：`n$scannedBin`n`n将直接安装桌面版。"
    } else {
        $choice = Show-Question "未检测到本机安装的 DeepSeek Harness。`n`n请选择：`n[是] 请帮助我安装好 DeepSeek Harness`n[否] 我手动输入 DeepSeek Harness 的安装路径`n[取消] 退出安装"
        if ($choice -eq [System.Windows.Forms.DialogResult]::Cancel) { exit 0 }

        if ($choice -eq [System.Windows.Forms.DialogResult]::Yes) {
            Show-Info "将检测 Node.js 依赖并自动安装 DeepSeek Harness，请稍候..."
            $installed = Invoke-HelpInstall
            if (-not $installed) {
                Show-Error "DeepSeek Harness 安装未能完成。桌面版安装已中止。`n`n您也可以稍后手动安装：npm install -g @deepseek-ai/dsh，再重新运行本安装程序。"
                exit 1
            }
            $scannedBin = $installed
        } else {
            # 手动输入路径
            $path = Show-InputBox "请输入 DeepSeek Harness 的安装路径（可以是 bin.js 文件、@deepseek-ai\dsh 包目录、node_modules 所在目录或 dsh 可执行文件所在目录）："
            if ([string]::IsNullOrWhiteSpace($path)) { exit 0 }
            $userDshPath = Resolve-DshPath $path
            while (-not $userDshPath) {
                $again = Show-Question "您提供的路径下未发现 DeepSeek Harness 程序：`n$path`n`n[是] 仍然安装（路径下没有程序，桌面版可能无法正常使用）`n[否] 重新输入路径`n[取消] 取消安装", "路径未找到", [System.Windows.Forms.MessageBoxButtons]::YesNoCancel
                if ($again -eq [System.Windows.Forms.DialogResult]::Cancel) { exit 0 }
                if ($again -eq [System.Windows.Forms.DialogResult]::Yes) {
                    $insisted = $true
                    $userDshPath = $path   # 尊重用户意愿，仍写入 config
                    break
                }
                $path = Show-InputBox "请重新输入 DeepSeek Harness 的安装路径："
                if ([string]::IsNullOrWhiteSpace($path)) { exit 0 }
                $userDshPath = Resolve-DshPath $path
            }
            if ($userDshPath -and -not $insisted) { Show-Info "路径验证通过：`n$userDshPath" }
        }
    }
}

# --- 阶段 2：执行安装 ---
if ($userDshPath) {
    Install-DesktopApp -DshBinPath $userDshPath
} else {
    Install-DesktopApp -DshBinPath $null
}

$uninstallerPath = Join-Path $installDir "卸载 DeepSeek Harness 桌面版.vbs"
$targetVbs = Join-Path $installDir "启动 DeepSeek Harness.vbs"

if ($silent) {
    Write-Log "安装完成: $installDir"
    Write-Log "卸载程序: $uninstallerPath"
    exit 0
}

if ($insisted) {
    Show-Error "安装已完成，但请注意：`n您提供的路径下没有发现 DeepSeek Harness 程序，桌面版可能无法正常使用。`n`n您可以在 DeepSeek Harness 正确安装后重新运行本安装程序，`n或使用以下卸载程序卸载桌面版：`n$uninstallerPath", "安装完成（警告）"
} else {
    $launch = Show-Question "安装完成！`n`n安装位置：$installDir`n卸载程序：$uninstallerPath`n`n是否立即启动 DeepSeek Harness 桌面版？", "安装完成", [System.Windows.Forms.MessageBoxButtons]::YesNo
    if ($launch -eq [System.Windows.Forms.DialogResult]::Yes) {
        Start-Process wscript.exe -ArgumentList "`"$targetVbs`""
    }
}
exit 0
