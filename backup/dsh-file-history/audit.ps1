# 审计脚本：外部 agent 改完回传的版本，先过这一关再提交
#
# 用法（Windows PowerShell 5.1 即可）：
#   # 1) 审计当前仓库（基线自检）
#   powershell -ExecutionPolicy Bypass -File audit.ps1
#   # 2) 审计回传的版本（目录或解压后的 zip 都行）
#   powershell -ExecutionPolicy Bypass -File audit.ps1 -Path "D:\incoming\dsh-file-history"
#
# 判据分两类：
#   A. 机械检查（脚本自动判定）：必需文件、package.json 元数据、语法、绝对路径/密钥泄漏、
#      .ps1 的 UTF-8 BOM、inject 项、测试套件、npm pack 内容。
#   B. 基线差异（-Path 与基线不同时打印）：新增/删除/修改的文件，供人工逐条过。
#
# 退出码：0 = 全部通过；1 = 有失败项；2 = 环境问题（node/npm 不可用等）。

param(
    [string]$Path = $PSScriptRoot,
    [string]$BaselineDir = $PSScriptRoot,
    [switch]$SkipInstall,
    [switch]$SkipPack
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$checks = New-Object System.Collections.Generic.List[object]
function Check([string]$item, [bool]$pass, [string]$detail) {
    $checks.Add([pscustomobject]@{ 判据 = $item; 结果 = $(if ($pass) { 'PASS' } else { 'FAIL' }); 细节 = $detail })
    $color = if ($pass) { 'Green' } else { 'Red' }
    Write-Host ("  [{0}] {1}{2}" -f $(if ($pass) { 'PASS' } else { 'FAIL' }), $item, $(if ($detail) { ' — ' + $detail } else { '' })) -ForegroundColor $color
}
function Head([string]$text) { Write-Host ''; Write-Host ("== " + $text + " " + ('=' * [Math]::Max(2, 56 - $text.Length))) -ForegroundColor Cyan }

$target = (Resolve-Path -LiteralPath $Path).Path
$baseline = (Resolve-Path -LiteralPath $BaselineDir).Path
if ($target -eq $baseline) { $sameDir = $true } else { $sameDir = $false }

Head "审计目标：$target"
if (-not $sameDir) { Write-Host ("  基线：$baseline") -ForegroundColor Gray }

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Write-Error 'node 不可用，无法运行测试'; exit 2 }
if (-not $SkipPack -and -not (Get-Command npm -ErrorAction SilentlyContinue)) { Write-Error 'npm 不可用（可用 -SkipPack 跳过打包检查）'; exit 2 }

# ── A1. 必需文件 ─────────────────────────────────────────────
Head 'A1. 必需文件'
$required = @(
    'package.json', 'README.md', 'LICENSE', '.gitignore', '.gitattributes',
    'lib/index.js', 'lib/client.js',
    'install.ps1', 'monitor.ps1', 'verify.ps1', 'after-restart-check.ps1',
    'selftest.mjs', 'host-contract-check.mjs',
    'HANDOVER.md', 'PUBLISH.md', '.github/workflows/ci.yml'
)
$missing = @()
foreach ($rel in $required) {
    if (-not (Test-Path (Join-Path $target $rel))) { $missing += $rel }
}
Check '必需文件齐全' ($missing.Count -eq 0) $(if ($missing.Count) { '缺: ' + ($missing -join ', ') } else { "$($required.Count) 个文件都在" })

# ── A2. package.json 元数据 ──────────────────────────────────
Head 'A2. package.json'
$pkgPath = Join-Path $target 'package.json'
if (Test-Path $pkgPath) {
    try {
        $pkg = Get-Content $pkgPath -Raw -Encoding utf8 | ConvertFrom-Json
        Check 'name = dsh-file-history' ($pkg.name -eq 'dsh-file-history') $pkg.name
        Check 'type = module' ($pkg.type -eq 'module') $pkg.type
        Check 'main = lib/index.js' ($pkg.main -eq 'lib/index.js') $pkg.main
        Check 'exports ./client 存在' ($null -ne $pkg.exports -and $null -ne $pkg.exports.'./client') $(if ($pkg.exports) { ($pkg.exports.PSObject.Properties.Name -join ',') } else { '' })
        Check 'dsh.client.platform = web' ($pkg.dsh.client.platform -eq 'web') $pkg.dsh.client.platform
        Check 'license = MIT' ($pkg.license -eq 'MIT') $pkg.license
        Check 'files 含 lib' (@($pkg.files) -contains 'lib') (@($pkg.files) -join ',')
        Check 'repository/homepage 已填' ($null -ne $pkg.repository -and $null -ne $pkg.homepage) $pkg.repository.url
        Check 'dependencies 含 cordis/schemastery' (@($pkg.dependencies.PSObject.Properties.Name) -contains '@deepseek-ai/cordis' -and @($pkg.dependencies.PSObject.Properties.Name) -contains '@deepseek-ai/schemastery') (@($pkg.dependencies.PSObject.Properties.Name) -join ',')
        Check '版本号非 0.0.0' ($pkg.version -ne '0.0.0' -and $pkg.version -ne '') $pkg.version
    } catch { Check 'package.json 可解析' $false $_.Exception.Message }
} else { Check 'package.json 可解析' $false '文件不存在' }

# ── A3. 语法 ────────────────────────────────────────────────
Head 'A3. 语法'
foreach ($rel in @('lib/index.js', 'lib/client.js', 'selftest.mjs', 'host-contract-check.mjs')) {
    $file = Join-Path $target $rel
    if (-not (Test-Path $file)) { Check "node --check $rel" $false '文件不存在'; continue }
    $null = & node --check $file 2>&1
    Check "node --check $rel" ($LASTEXITCODE -eq 0) $(if ($LASTEXITCODE -ne 0) { '语法错误' } else { '' })
}
foreach ($file in (Get-ChildItem $target -Filter *.ps1 -File)) {
    $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    Check ("UTF-8 BOM：" + $file.Name) $hasBom $(if ($hasBom) { '' } else { 'PS 5.1 会按 ANSI 读取，中文会破坏语法' })
}

# ── A4. 绝对路径 / 密钥泄漏 ─────────────────────────────────
Head 'A4. 绝对路径与密钥'
$scanExt = @('.js', '.mjs', '.ps1', '.json', '.md', '.yml', '.yaml', '.psd1', '.psm1')
$scanFiles = Get-ChildItem $target -Recurse -File -Force |
    Where-Object {
        $scanExt -contains $_.Extension -and
        $_.FullName -notmatch '\\(node_modules|\.git)\\' -and
        $_.Name -ne 'package-lock.json' -and
        # 扫描器自身含有这些检测字面量，必须排除（否则永远自报失败）
        $_.Name -ne 'audit.ps1' -and
        $_.FullName -notmatch '\\e2e\\ws\\'
    }
$pathHits = @()
$secretHits = @()
foreach ($file in $scanFiles) {
    $text = Get-Content $file.FullName -Raw -Encoding utf8 -ErrorAction SilentlyContinue
    if ($null -eq $text) { continue }
    if ($text -match '[A-Za-z]:[\\/]+Users[\\/]' -or $text -match 'twinblade' -or $text -match '_npx[\\/][0-9a-f]{10,}') {
        $pathHits += $file.FullName.Substring($target.Length).TrimStart('\', '/')
    }
    if ($text -match 'ghp_[A-Za-z0-9]{20,}' -or $text -match 'github_pat_[A-Za-z0-9_]{20,}' -or $text -match 'sk-[A-Za-z0-9]{20,}' -or $text -match 'AKIA[0-9A-Z]{16}' -or $text -match 'BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY' -or $text -match '(?i)(api[_-]?key|password|secret)\s*[:=]\s*["''][^"'']{12,}') {
        $secretHits += $file.FullName.Substring($target.Length).TrimStart('\', '/')
    }
}
Check '无本机绝对路径 / 用户名 / npx 缓存 hash' ($pathHits.Count -eq 0) $(if ($pathHits.Count) { '命中: ' + (($pathHits | Select-Object -Unique) -join ', ') } else { "扫描 $($scanFiles.Count) 个文件" })
Check '无密钥/令牌迹象' ($secretHits.Count -eq 0) $(if ($secretHits.Count) { '命中: ' + (($secretHits | Select-Object -Unique) -join ', ') } else { '' })

# ── A5. inject 项一致性 ─────────────────────────────────────
Head 'A5. inject 项（漏一个就加载失败或面板失效）'
$instText = if (Test-Path (Join-Path $target 'install.ps1')) { Get-Content (Join-Path $target 'install.ps1') -Raw -Encoding utf8 } else { '' }
$e2eText = if (Test-Path (Join-Path $target 'e2e/patch.yml')) { Get-Content (Join-Path $target 'e2e/patch.yml') -Raw -Encoding utf8 } else { '' }
$indexText = if (Test-Path (Join-Path $target 'lib/index.js')) { Get-Content (Join-Path $target 'lib/index.js') -Raw -Encoding utf8 } else { '' }
foreach ($pair in @(
    @('install.ps1 写入的 inject', $instText, 'inject: \[tools, settings, timer, agents\]'),
    @('e2e/patch.yml 的 inject', $e2eText, 'inject: \[tools, settings, timer, agents\]'),
    @('lib/index.js 导出的 inject', $indexText, "inject = \['tools', 'settings', 'timer', 'agents'\]")
)) {
    Check $pair[0] ($pair[1] -match $pair[2]) $(if ($pair[1] -match $pair[2]) { '' } else { '缺少 timer 或 agents' })
}

# ── A6. 测试 ────────────────────────────────────────────────
Head 'A6. 测试套件'
$nodeModules = Join-Path $target 'node_modules'
if (-not (Test-Path $nodeModules) -and -not $SkipInstall) {
    Write-Host '  安装依赖（公共 npm）…' -ForegroundColor Gray
    Push-Location $target
    $null = & npm install --no-audit --no-fund 2>&1
    Pop-Location
}
if (Test-Path $nodeModules) {
    Push-Location $target
    $selfOut = & node selftest.mjs 2>&1
    $selfExit = $LASTEXITCODE
    $selfLine = ($selfOut | Where-Object { $_ -match 'passed' } | Select-Object -Last 1)
    Check 'selftest.mjs' ($selfExit -eq 0) $(if ($selfLine) { $selfLine.Trim() } else { "exit=$selfExit" })
    $contractOut = & node host-contract-check.mjs 2>&1
    $contractExit = $LASTEXITCODE
    $contractLine = ($contractOut | Where-Object { $_ -match 'passed' } | Select-Object -Last 1)
    Check 'host-contract-check.mjs' ($contractExit -eq 0) $(if ($contractLine) { $contractLine.Trim() } else { "exit=$contractExit" })
    Pop-Location
} else {
    Check 'selftest.mjs' $false 'node_modules 不存在（未安装依赖；或用 -SkipInstall 跳过）'
    Check 'host-contract-check.mjs' $false '同上'
}

# ── A7. 打包内容 ────────────────────────────────────────────
if (-not $SkipPack) {
    Head 'A7. npm pack 内容'
    Push-Location $target
    $packOut = & npm pack --dry-run 2>&1
    Pop-Location
    $packText = ($packOut | Out-String)
    $totalLine = ($packOut | Where-Object { $_ -match 'total files:' } | Select-Object -Last 1)
    Check 'npm pack 成功' ($packText -match 'dsh-file-history-') $(if ($totalLine) { $totalLine.Trim() } else { '' })
    Check '包内含 lib/index.js' ($packText -match 'lib[/\\]index\.js') ''
    Check '包内含 lib/client.js' ($packText -match 'lib[/\\]client\.js') ''
}

# ── B. 与基线的差异 ─────────────────────────────────────────
function Get-Hashes([string]$root) {
    $map = @{}
    Get-ChildItem $root -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\(node_modules|\.git)\\' -and $_.FullName -notmatch '\\e2e\\ws\\' } |
        ForEach-Object {
            $rel = $_.FullName.Substring($root.Length).TrimStart('\', '/').Replace('\', '/')
            $map[$rel] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
        }
    return $map
}

if (-not $sameDir) {
    Head 'B. 与基线的差异（人工过）'
    $baseMap = Get-Hashes $baseline
    $targetMap = Get-Hashes $target
    $added = @($targetMap.Keys | Where-Object { -not $baseMap.ContainsKey($_) } | Sort-Object)
    $removed = @($baseMap.Keys | Where-Object { -not $targetMap.ContainsKey($_) } | Sort-Object)
    $changed = @($targetMap.Keys | Where-Object { $baseMap.ContainsKey($_) -and $baseMap[$_] -ne $targetMap[$_] } | Sort-Object)
    Write-Host ("  新增 {0} 个 / 删除 {1} 个 / 修改 {2} 个" -f $added.Count, $removed.Count, $changed.Count)
    foreach ($f in $added) { Write-Host ("    + " + $f) -ForegroundColor Green }
    foreach ($f in $removed) { Write-Host ("    - " + $f) -ForegroundColor Yellow }
    foreach ($f in $changed) { Write-Host ("    ~ " + $f) -ForegroundColor Cyan }
    if ($added.Count + $removed.Count + $changed.Count -eq 0) { Write-Host '    （与基线逐字节一致）' -ForegroundColor Green }
}

# ── 结论 ────────────────────────────────────────────────────
Head '结论'
$failed = @($checks | Where-Object { $_.结果 -eq 'FAIL' })
$checks | Format-Table -AutoSize
if ($failed.Count -eq 0) {
    Write-Host ("[audit] PASS：{0} 项机械判据全部通过。" -f $checks.Count) -ForegroundColor Green
    if (-not $sameDir) { Write-Host '[audit] 别忘了人工过一遍上面的 B 段差异，再决定是否合并。' -ForegroundColor Yellow }
    exit 0
}
Write-Host ("[audit] FAIL：{0} 项未通过。" -f $failed.Count) -ForegroundColor Red
foreach ($f in $failed) { Write-Host ("  · " + $f.判据 + " — " + $f.细节) -ForegroundColor Red }
exit 1
