# dsh-file-history 观测面板
# 用法（普通 PowerShell 窗口；不要从 dsh 的工具里调用）：
#   powershell -ExecutionPolicy Bypass -File monitor.ps1                 # 一次看清：当前项目是否在正常备份
#   powershell -ExecutionPolicy Bypass -File monitor.ps1 -Watch          # 实时盯梢：有新备份就实时打印
#   powershell -ExecutionPolicy Bypass -File monitor.ps1 -Scan           # 扫一遍本机所有项目的备份区
#   powershell -ExecutionPolicy Bypass -File monitor.ps1 -Project "D:\proj" -Watch
#
# 判据（面板里逐条打勾）：插件已安装 → patch 已登记 → 备份目录已创建 → status.json 存在
#   → status 为 ok 且时间戳新鲜 → 无 lastError → 最近有实际快照/还原动作。

param(
    # 默认项目：优先取环境变量 FH_PROJECT（避免路径带空格时被 Start-Process 的参数拆分吃掉），否则用当前目录。
    [string]$Project = $(if ($env:FH_PROJECT) { $env:FH_PROJECT } else { (Get-Location).Path }),
    [string]$DshHome = (Join-Path $env:USERPROFILE '.dsh'),
    [string]$Profile = 'web',
    [int]$IntervalSec = 3,
    [int]$FreshMinutes = 5,
    [switch]$Watch,
    [switch]$Scan
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Write-Head([string]$text) { Write-Host ''; Write-Host ("== " + $text + " " + ("=" * [Math]::Max(2, 60 - $text.Length))) -ForegroundColor Cyan }
function Write-Ok([string]$text) { Write-Host ("  [OK]   " + $text) -ForegroundColor Green }
function Write-Bad([string]$text) { Write-Host ("  [!!]   " + $text) -ForegroundColor Red }
function Write-Warn([string]$text) { Write-Host ("  [~]    " + $text) -ForegroundColor Yellow }
function Write-Info([string]$text) { Write-Host ("  " + $text) -ForegroundColor Gray }

function Get-Status([string]$project) {
    $statusPath = Join-Path $project '.dsh-backup\_dsh-file-history\status.json'
    if (-not (Test-Path $statusPath)) { return $null }
    try { return (Get-Content $statusPath -Raw -Encoding utf8 | ConvertFrom-Json) } catch { return $null }
}

function Get-BackupStat([string]$project) {
    $metaDir = Join-Path $project '.dsh-backup\_dsh-file-history'
    if (-not (Test-Path $metaDir)) { return [pscustomobject]@{ Count = 0; Files = 0; Bytes = 0 } }
    $sidecars = Get-ChildItem $metaDir -Filter '*.json' -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne 'status.json' }
    $bytes = 0
    foreach ($item in (Get-ChildItem (Join-Path $project '.dsh-backup') -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike '*.json' })) {
        $bytes += $item.Length
    }
    return [pscustomobject]@{ Count = @($sidecars).Count; Files = @($sidecars).Count; Bytes = $bytes }
}

function Format-Size([long]$bytes) {
    if ($bytes -lt 1024) { return "$bytes B" }
    if ($bytes -lt 1048576) { return ("{0:N1} KB" -f ($bytes / 1024)) }
    return ("{0:N1} MB" -f ($bytes / 1048576))
}

function Show-ProjectReport([string]$project) {
    Write-Head ("项目: " + $project)
    $backupRoot = Join-Path $project '.dsh-backup'
    $metaDir = Join-Path $backupRoot '_dsh-file-history'
    $statusPath = Join-Path $metaDir 'status.json'
    $manifestPath = Join-Path $metaDir 'manifest.jsonl'
    $checks = @()

    $plugin = Join-Path $DshHome "profiles\$Profile\node_modules\dsh-file-history\lib\index.js"
    $checks += [pscustomobject]@{ 判据 = '插件已安装'; 结果 = (Test-Path $plugin); 细节 = $plugin }
    $patch = Join-Path $DshHome "profiles\$Profile\cordis.patch.yml"
    $patchOk = (Test-Path $patch) -and ((Get-Content $patch -Raw -Encoding utf8) -match 'dsh-file-history')
    $checks += [pscustomobject]@{ 判据 = 'patch 已登记'; 结果 = $patchOk; 细节 = $patch }

    $status = Get-Status $project
    $stat = Get-BackupStat $project
    $checks += [pscustomobject]@{ 判据 = '备份目录已创建'; 结果 = (Test-Path $backupRoot); 细节 = $backupRoot }
    $checks += [pscustomobject]@{ 判据 = 'status.json 存在'; 结果 = ($null -ne $status); 细节 = $statusPath }

    $fresh = $false
    $atText = '(无)'
    if ($status -and $status.atMs) {
        $atText = $status.at
        # Windows PowerShell 5.1 没有 [datetime]::UnixEpoch，用 epoch 基准时间换算。
        $epoch = (Get-Date '1970-01-01T00:00:00Z').ToUniversalTime()
        $nowMs = [double]((Get-Date).ToUniversalTime() - $epoch).TotalMilliseconds
        $ageMin = ($nowMs - [double]$status.atMs) / 60000
        $fresh = ($ageMin -le $FreshMinutes)
        $checks += [pscustomobject]@{ 判据 = "时间戳新鲜(<=${FreshMinutes}分钟)"; 结果 = $fresh; 细节 = ("最后活动 " + $atText + "，约 " + [Math]::Round($ageMin, 1) + ' 分钟前') }
    } else {
        $checks += [pscustomobject]@{ 判据 = "时间戳新鲜(<=${FreshMinutes}分钟)"; 结果 = $false; 细节 = '还没有任何备份动作' }
    }
    $checks += [pscustomobject]@{ 判据 = 'status = ok'; 结果 = ($status -and $status.status -eq 'ok'); 细节 = if ($status) { [string]$status.status } else { '(无)' } }
    $noError = ($null -eq $status -or $null -eq $status.lastError)
    $checks += [pscustomobject]@{ 判据 = '无 lastError'; 结果 = $noError; 细节 = if ($noError) { '无' } else { [string]$status.lastError.reason } }
    $checks += [pscustomobject]@{ 判据 = '已有备份记录'; 结果 = ($stat.Count -gt 0); 细节 = ("备份文件 " + $stat.Count + " 份，占用 " + (Format-Size $stat.Bytes)) }

    $checks | Format-Table -AutoSize

    if ($status) {
        Write-Info ("备份目录   : " + $status.backupDir)
        Write-Info ("备份次数   : " + $status.snapshots)
        Write-Info ("每文件代数 : " + $status.retainedPerFile)
        if ($status.lastBackup) { Write-Info ("最近备份   : " + $status.lastBackup.at + "  ← " + $status.lastBackup.path) }
        if ($status.lastRestore) { Write-Info ("最近还原   : " + $status.lastRestore.at + "  ← " + $status.lastRestore.path) }
    }
    if (Test-Path $manifestPath) {
        Write-Head '最近 8 条备份/还原流水（manifest.jsonl）'
        Get-Content $manifestPath -Encoding utf8 -Tail 8 | ForEach-Object {
            try {
                $row = $_ | ConvertFrom-Json
                $color = if ($row.kind -eq 'restore') { 'Cyan' } elseif ($row.kind -eq 'revert_turn') { 'Magenta' } else { 'White' }
                Write-Host ("  " + $row.at + "  " + $row.kind.PadRight(11) + " " + [System.IO.Path]::GetFileName($row.source)) -ForegroundColor $color
            } catch { Write-Host ("  " + $_) -ForegroundColor DarkGray }
        }
    }
    Write-Head '结论'
    $failed = @($checks | Where-Object { -not $_.结果 })
    if ($failed.Count -eq 0) {
        Write-Ok '备份系统正常工作：改文件前后都能在 .dsh-backup 里看到对应备份。'
    } elseif ($failed.Count -le 2 -and ($failed.判据 -contains '已有备份记录' -or $failed.判据 -like '时间戳新鲜*')) {
        Write-Warn '插件已加载，但本项目最近没有备份动作（改一个已存在的文件后应立刻出现记录）。'
    } else {
        Write-Bad ('有 ' + $failed.Count + ' 项未通过：' + (($failed | ForEach-Object { $_.判据 }) -join '、') + '。若插件未加载，请重启 dsh 服务后重跑本脚本。')
    }
}

function Show-Scan {
    Write-Head '本机各项目的备份区（.dsh-backup）'
    $roots = @(
        (Join-Path $env:USERPROFILE 'Documents'),
        (Join-Path $env:USERPROFILE 'Desktop'),
        'C:\Users\twinblade\Documents\deeepseek harness',
        (Get-Location).Path
    ) | Select-Object -Unique
    $rows = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $found = Get-ChildItem $root -Directory -Recurse -Depth 3 -Filter '.dsh-backup' -ErrorAction SilentlyContinue
        foreach ($dir in $found) {
            $projectDir = Split-Path $dir.FullName -Parent
            $status = Get-Status $projectDir
            $stat = Get-BackupStat $projectDir
            $rows += [pscustomobject]@{
                项目   = $projectDir
                最后活动 = if ($status) { $status.at } else { '(无 status)' }
                备份数 = $stat.Count
                占用   = Format-Size $stat.Bytes
                错误   = if ($status -and $status.lastError) { '有' } else { '无' }
            }
        }
    }
    if ($rows.Count -eq 0) { Write-Warn '没找到任何 .dsh-backup 目录。'; return }
    $rows | Sort-Object 最后活动 -Descending | Format-Table -AutoSize
    Write-Info '兜底目录（项目外文件的备份）: ' + (Join-Path $DshHome 'file-history')
}

function Watch-Project([string]$project) {
    $metaDir = Join-Path $project '.dsh-backup\_dsh-file-history'
    $manifestPath = Join-Path $metaDir 'manifest.jsonl'
    $statusPath = Join-Path $metaDir 'status.json'
    $seen = 0
    if (Test-Path $manifestPath) { $seen = @(Get-Content $manifestPath -Encoding utf8 -ErrorAction SilentlyContinue).Count }
    $status = Get-Status $project
    $lastAt = if ($status) { $status.atMs } else { 0 }

    Write-Head '实时盯梢中（Ctrl+C 退出）'
    Write-Info ('项目      : ' + $project)
    Write-Info ('备份目录  : ' + (Join-Path $project '.dsh-backup'))
    Write-Info ('起始流水  : 已有 ' + $seen + ' 条记录')
    Write-Host ''
    Write-Host '  现在去让 agent 改一个已存在的文件（或自己编辑一下），这里会立刻打印：' -ForegroundColor Yellow
    Write-Host ''

    $tick = 0
    while ($true) {
        Start-Sleep -Seconds $IntervalSec
        $tick += 1
        if (Test-Path $manifestPath) {
            $lines = @(Get-Content $manifestPath -Encoding utf8 -ErrorAction SilentlyContinue)
            if ($lines.Count -gt $seen) {
                for ($i = $seen; $i -lt $lines.Count; $i += 1) {
                    try {
                        $row = $lines[$i] | ConvertFrom-Json
                        $color = if ($row.kind -eq 'restore') { 'Cyan' } elseif ($row.kind -eq 'revert_turn') { 'Magenta' } else { 'Green' }
                        $line = "  " + $row.at + "  " + $row.kind.PadRight(11) + " " + $row.source
                        if ($row.backup) { $line += "`n            → " + $row.backup }
                        Write-Host $line -ForegroundColor $color
                    } catch {
                        Write-Host ("  " + $lines[$i]) -ForegroundColor DarkYellow
                    }
                }
                $seen = $lines.Count
            }
        }
        $current = Get-Status $project
        if ($current -and $current.atMs -ne $lastAt) {
            $lastAt = $current.atMs
            if ($current.lastError) { Write-Warn ('插件报告错误: ' + $current.lastError.reason) }
        }
        if ($tick % 10 -eq 0) {
            $stat = Get-BackupStat $project
            Write-Host ('  · 心跳 ' + (Get-Date -Format 'HH:mm:ss') + '  备份 ' + $stat.Count + ' 份 / ' + (Format-Size $stat.Bytes) + '  流水 ' + $seen + ' 条') -ForegroundColor DarkGray
        }
    }
}

if ($Scan) { Show-Scan }
elseif ($Watch) { Watch-Project $Project }
else { Show-ProjectReport $Project }
