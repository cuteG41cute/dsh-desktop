<#
  build-msi.ps1 — 从开发目录直接打包 Windows 安装包（MSI）

  用法（在 dsh-desktop\msi 目录下）：
    powershell -NoProfile -ExecutionPolicy Bypass -File build-msi.ps1
    powershell ... -File build-msi.ps1 -WixExe <wix.exe> -ExtPath <WixToolset.UI.wixext.dll>

  产物：..\dist\DeepSeek Harness 桌面版 <版本>.msi
        <版本> 取自 product.wxs 的 Version 属性；
        ProductCode 也必须随版本更换（UpgradeCode 保持不变，才能自动升级旧版本）。

  暂存目录：本目录的 .stage\（每次构建重建，可随时删除）
    .stage\files\...            安装到安装根的启动器/入口
    .stage\files\dsh-desktop\   安装到 dsh-desktop\ 子目录的包装程序
  载荷来源：..\（开发目录）中的启动器与包装程序 + 本目录 payload\README.md
#>
[CmdletBinding()]
param(
    [string]$WixExe = "",
    [string]$ExtPath = "",
    [string]$Culture = "zh-CN"
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$devRoot = Split-Path $here -Parent          # dsh-desktop\
$repoRoot = Split-Path $devRoot -Parent      # 仓库根（.tmp 工具目录在这里）
$stage = Join-Path $here ".stage"
$outDir = Join-Path $devRoot "dist"

function Write-Step { param([string]$Message) Write-Host ("==> " + $Message) }

# ---- 1. 定位 WiX 工具 ----
if (-not $WixExe) {
    $candidates = @(
        (Join-Path $repoRoot ".tmp\wix-cli\PFiles64\WiX Toolset v7.0\bin\wix.exe"),
        (Join-Path $repoRoot ".tmp\wix\wix.exe")
    )
    foreach ($c in $candidates) { if (Test-Path $c) { $WixExe = $c; break } }
    if (-not $WixExe) {
        $cmd = Get-Command wix -ErrorAction SilentlyContinue
        if ($cmd) { $WixExe = $cmd.Source }
    }
}
if (-not $WixExe -or -not (Test-Path $WixExe)) {
    throw "找不到 wix.exe。请用 -WixExe 指定路径（WiX v4+ 命令行工具，dotnet tool install --global wix）。"
}

if (-not $ExtPath) {
    $candidates = @(
        (Join-Path $here "tools\WixToolset.UI.wixext.dll"),
        (Join-Path $repoRoot ".tmp\WixToolset.UI.wixext.dll")
    )
    foreach ($c in $candidates) { if (Test-Path $c) { $ExtPath = $c; break } }
}
if (-not $ExtPath -or -not (Test-Path $ExtPath)) {
    throw "找不到 WixToolset.UI.wixext.dll。请用 -ExtPath 指定（wix extension add WixToolset.UI.wixext 后可取其 dll）。"
}

# ---- 2. 读取版本号 ----
$wxsText = [System.IO.File]::ReadAllText((Join-Path $here "product.wxs"), [System.Text.UTF8Encoding]::new($false))
$version = ([regex]::Match($wxsText, 'Version="([^"]+)"')).Groups[1].Value
if (-not $version) { throw "product.wxs 里没有 Version 属性。" }
$productCode = ([regex]::Match($wxsText, 'ProductCode="([^"]+)"')).Groups[1].Value
$msiName = "DeepSeek Harness 桌面版 $version.msi"
Write-Step "版本 $version / ProductCode $productCode"

# ---- 2.5 载荷自检 ----
# 中文 .ps1 必须是 UTF-8 **带 BOM**：PowerShell 5.1 读无 BOM 的中文脚本会按 ANSI 解码，
# 轻则乱码、重则语法错误（脚本直接跑不起来）。历史上这里踩过两次坑，故打包前强制检查。
function Assert-Utf8Bom {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    $nonAscii = $false
    foreach ($b in $bytes) { if ($b -gt 127) { $nonAscii = $true; break } }
    if ($nonAscii -and -not $bom) {
        throw "载荷 $Path 含非 ASCII 字符但没有 UTF-8 BOM；请补写 EF BB BF 后重新打包。"
    }
}
Assert-Utf8Bom (Join-Path $devRoot "launcher.ps1")
# ---- 3. 重建暂存目录 ----
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $stage "files\dsh-desktop") | Out-Null

foreach ($name in @("product.wxs", "actions.vbs", "dsh_zh-CN.wxl")) {
    Copy-Item (Join-Path $here $name) -Destination $stage -Force
}

# 安装根：启动器与入口
$rootPayload = @{
    "launcher.ps1"                  = (Join-Path $devRoot "launcher.ps1")
    "启动 DeepSeek Harness.vbs"       = (Join-Path $devRoot "启动 DeepSeek Harness.vbs")
    "Start DeepSeek Harness.vbs"    = (Join-Path $devRoot "Start DeepSeek Harness.vbs")
    "README.md"                     = (Join-Path $here "payload\README.md")
}
foreach ($name in $rootPayload.Keys) {
    $src = $rootPayload[$name]
    if (-not (Test-Path $src)) { throw "缺少载荷文件：$src" }
    Copy-Item $src -Destination (Join-Path $stage "files") -Force
}

# dsh-desktop\ 子目录：WebView2 包装程序（与 product.wxs 的 File 清单一一对应）
$appPayload = @(
    "DSH Desktop.exe", "App.cs", "app.ico", "icon-source.png",
    "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.Core.xml",
    "Microsoft.Web.WebView2.WinForms.dll", "Microsoft.Web.WebView2.WinForms.xml",
    "WebView2Loader.dll"
)
foreach ($name in $appPayload) {
    $src = Join-Path $devRoot $name
    if (-not (Test-Path $src)) { throw "缺少载荷文件：$src" }
    Copy-Item $src -Destination (Join-Path $stage "files\dsh-desktop") -Force
}
Write-Step "载荷已暂存到 $stage"

# ---- 4. 构建 ----
New-Item -ItemType Directory -Force $outDir | Out-Null
$outPath = Join-Path $outDir $msiName
if (Test-Path $outPath) { Remove-Item $outPath -Force }

Push-Location $stage
try {
    & $WixExe build "product.wxs" -o $outPath -ext $ExtPath -arch x64 -culture $Culture -loc "dsh_zh-CN.wxl" -pdb (Join-Path $stage "dsh-desktop.wixpdb") |
        Where-Object { $_ -notmatch "WIX1163" } | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "wix build 失败（退出码 $LASTEXITCODE）。" }
} finally {
    Pop-Location
}

$file = Get-Item $outPath
Write-Step ("完成：{0}（{1:N0} 字节）" -f $file.FullName, $file.Length)
