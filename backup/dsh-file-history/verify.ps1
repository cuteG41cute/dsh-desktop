# dsh-file-history 端到端验证脚本
# 用途：在一个**独立**的 dsh 实例里跑一次真实 agent，确认「覆盖前自动快照 + 还原」在 harness 内部生效。
# 不依赖、也不影响正在运行的 127.0.0.1:3080 服务。
#
# 用法（在普通 PowerShell 窗口里跑，不要从 dsh 的工具里调用）：
#   powershell -ExecutionPolicy Bypass -File verify.ps1
#   powershell -ExecutionPolicy Bypass -File verify.ps1 -Keep

param(
    [string]$Profile = 'rescue',
    [string]$Patch = (Join-Path $PSScriptRoot 'e2e\patch.yml'),
    [string]$WorkDir = (Join-Path $PSScriptRoot 'e2e\ws'),
    [string]$HistoryDir = (Join-Path $env:USERPROFILE '.dsh\file-history'),
    [switch]$Keep
)

$ErrorActionPreference = 'Stop'
$bin = Join-Path $env:LOCALAPPDATA 'npm-cache\_npx\1e7f6d9597241db0\node_modules\@deepseek-ai\dsh\lib\bin.js'
if (-not (Test-Path $bin)) { throw "找不到 dsh 入口: $bin" }

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
$target = Join-Path $WorkDir 'e2e.txt'
Set-Content -Path $target -Value 'v0: 原始内容' -Encoding utf8

# 记录验证前的快照条目数，验证后对比增量，避免被历史条目干扰。
function Get-SnapshotCount([string]$path) {
    if (-not (Test-Path $HistoryDir)) { return 0 }
    $hits = Get-ChildItem $HistoryDir -Recurse -Filter 'meta.json' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\_sessions\\' } |
        ForEach-Object {
            try { (Get-Content $_.FullName -Raw -Encoding utf8 | ConvertFrom-Json).originalPath } catch { $null }
        } |
        Where-Object { $_ -eq $path }
    return @($hits).Count
}

$before = Get-SnapshotCount $target
Write-Host "[verify] 目标文件: $target"
Write-Host "[verify] 验证前快照数: $before"

$task = 'Work only in the current working directory. Step 1: read e2e.txt. Step 2: use the write tool to replace e2e.txt with exactly: v1 broken. Step 3: use the edit tool to change broken to worse. Step 4: call file_history with action=list, scope=session. Step 5: call file_history with action=restore, path=e2e.txt. Finally reply with exactly one line: SNAPSHOTS=<count> RESTORED=<status> AFTER=<literal current content of e2e.txt>'

Write-Host "[verify] 启动独立 dsh (profile=$Profile) 跑一次真实 agent…（首次几十秒 + 少量 token）"
$output = & node $bin --profile $Profile --patch $Patch $task 2>&1
$exit = $LASTEXITCODE
$output | ForEach-Object { Write-Host "  | $_" }

$after = Get-SnapshotCount $target
$content = (Get-Content $target -Raw -Encoding utf8).Trim()

Write-Host ''
Write-Host '===== 结论 ====='
Write-Host ("  exit_code     = {0}" -f $exit)
Write-Host ("  snapshots_new = {0}" -f ($after - $before))
Write-Host ("  final_content = {0}" -f $content)

$okSnap = ($after - $before) -ge 1
$okRestore = ($content -eq 'v0: 原始内容')
if ($okSnap -and $okRestore) {
    Write-Host '[verify] PASS：覆盖前自动快照已生效，且 file_history restore 把文件还原成功。'
    if (-not $Keep) { Remove-Item $WorkDir -Recurse -Force -ErrorAction SilentlyContinue }
    exit 0
}
Write-Host '[verify] FAIL：请把上面的输出（尤其是 dsh 的最后几行）发回来。'
exit 1
