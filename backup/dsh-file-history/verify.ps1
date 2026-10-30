# dsh-file-history 端到端验证脚本
# 用途：在一个**独立**的 dsh 实例里跑一次真实 agent，确认「覆盖前自动备份 + 还原」在 harness 内部生效。
# 不依赖、也不影响正在运行的 127.0.0.1:3080 服务。
#
# 用法（普通 PowerShell 窗口；不要从 dsh 的工具里调用）：
#   powershell -ExecutionPolicy Bypass -File verify.ps1
#   powershell -ExecutionPolicy Bypass -File verify.ps1 -Keep
#   powershell -ExecutionPolicy Bypass -File verify.ps1 -DshBin "C:\path\to\dsh\lib\bin.js"

param(
    [string]$Profile = 'rescue',
    [string]$Patch = (Join-Path $PSScriptRoot 'e2e\patch.yml'),
    [string]$WorkDir = (Join-Path $PSScriptRoot 'e2e\ws'),
    [string]$DshBin = '',
    [string]$DshHome = (Join-Path $env:USERPROFILE '.dsh'),
    [switch]$Keep
)

$ErrorActionPreference = 'Stop'

# 解析 dsh 入口：-DshBin > PATH 里的 dsh > npx 缓存里最新的那份（不写死某台机器的 hash 目录）。
function Resolve-Dsh {
    if ($DshBin) {
        if (-not (Test-Path $DshBin)) { throw " -DshBin 指向的文件不存在: $DshBin" }
        return [pscustomobject]@{ Command = $(if ($DshBin -match '\.(js|mjs|cjs)$') { 'node' } else { $DshBin }); Arg0 = $(if ($DshBin -match '\.(js|mjs|cjs)$') { $DshBin } else { $null }) }
    }
    $cmd = Get-Command dsh -ErrorAction SilentlyContinue
    if ($cmd) {
        if ($cmd.Source -match '\.(js|mjs|cjs)$') { return [pscustomobject]@{ Command = 'node'; Arg0 = $cmd.Source } }
        return [pscustomobject]@{ Command = $cmd.Source; Arg0 = $null }
    }
    $cacheRoots = @(
        (Join-Path $env:LOCALAPPDATA 'npm-cache\_npx'),
        (Join-Path $env:APPDATA 'npm-cache\_npx')
    )
    foreach ($root in $cacheRoots) {
        if (-not (Test-Path $root)) { continue }
        $found = Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName 'node_modules\@deepseek-ai\dsh\lib\bin.js' } |
            Where-Object { Test-Path $_ } |
            Sort-Object { (Get-Item $_).LastWriteTime } -Descending |
            Select-Object -First 1
        if ($found) { return [pscustomobject]@{ Command = 'node'; Arg0 = $found } }
    }
    throw '找不到 dsh 入口：请先安装（npm i -g @deepseek-ai/dsh），或用 -DshBin 显式指定 bin.js。'
}

$dsh = Resolve-Dsh
Write-Host ("[verify] dsh 入口: " + $dsh.Command + $(if ($dsh.Arg0) { ' ' + $dsh.Arg0 } else { '' }))
$profileDir = Join-Path $DshHome "profiles\$Profile"
if (-not (Test-Path $profileDir)) {
    throw "找不到 profile '$Profile' ($profileDir)。先创建：dsh --profile $Profile --from-default-profile web --dump-config"
}

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
$target = Join-Path $WorkDir 'e2e.txt'
Set-Content -Path $target -Value 'v0: 原始内容' -Encoding utf8

# 统计某个源文件在项目备份区里的备份份数（sidecar 元数据），避免被历史条目干扰。
function Get-BackupCount([string]$path, [string]$projectRoot) {
    $metaDir = Join-Path $projectRoot '.dsh-backup\_dsh-file-history'
    if (-not (Test-Path $metaDir)) { return 0 }
    $hits = Get-ChildItem $metaDir -Filter '*.json' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne 'status.json' } |
        ForEach-Object {
            try { (Get-Content $_.FullName -Raw -Encoding utf8 | ConvertFrom-Json).originalPath } catch { $null }
        } |
        Where-Object { $_ -eq $path }
    return @($hits).Count
}

$before = Get-BackupCount $target $WorkDir
Write-Host "[verify] 目标文件: $target"
Write-Host "[verify] 验证前该文件的备份数: $before"

$task = 'Work only in the current working directory. Step 1: read e2e.txt. Step 2: use the write tool to replace e2e.txt with exactly: v1 broken. Step 3: use the edit tool to change broken to worse. Step 4: call file_history with action=list, scope=session. Step 5: call file_history with action=restore, path=e2e.txt. Finally reply with exactly one line: SNAPSHOTS=<count> RESTORED=<status> AFTER=<literal current content of e2e.txt>'

Write-Host "[verify] 启动独立 dsh (profile=$Profile) 跑一次真实 agent…（首次几十秒 + 少量 token）"
$prefix = if ($dsh.Arg0) { @($dsh.Arg0) } else { @() }
$output = & $dsh.Command @prefix --profile $Profile --patch $Patch $task 2>&1
$exit = $LASTEXITCODE
$output | ForEach-Object { Write-Host "  | $_" }

$after = Get-BackupCount $target $WorkDir
$content = (Get-Content $target -Raw -Encoding utf8).Trim()
$statusPath = Join-Path $WorkDir '.dsh-backup\_dsh-file-history\status.json'
$statusText = if (Test-Path $statusPath) { (Get-Content $statusPath -Raw -Encoding utf8 | ConvertFrom-Json) } else { $null }

Write-Host ''
Write-Host '===== 结论 ====='
Write-Host ("  exit_code     = {0}" -f $exit)
Write-Host ("  backups_new   = {0}" -f ($after - $before))
Write-Host ("  final_content = {0}" -f $content)
Write-Host ("  status.json   = {0}" -f $(if ($statusText) { "at=$($statusText.at) snapshots=$($statusText.snapshots)" } else { '(未生成)' }))

$okSnap = ($after - $before) -ge 1
$okRestore = ($content -eq 'v0: 原始内容')
if ($okSnap -and $okRestore) {
    Write-Host '[verify] PASS：覆盖前自动备份已生效，且 file_history restore 把文件还原成功。'
    if (-not $Keep) { Remove-Item $WorkDir -Recurse -Force -ErrorAction SilentlyContinue }
    exit 0
}
Write-Host '[verify] FAIL：请把上面的输出（尤其是 dsh 的最后几行）发回来。'
exit 1
