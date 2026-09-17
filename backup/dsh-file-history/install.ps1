# dsh-file-history 安装 / 卸载脚本
# 把插件安装到一个 dsh profile 的 node_modules，并在该 profile 的 cordis.patch.yml 里登记加载项。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File install.ps1                 # 默认装到 web profile
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Profile web -Force
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Remove         # 卸载（已有快照不动）

param(
    [string]$Profile = 'web',
    [string]$DshHome = (Join-Path $env:USERPROFILE '.dsh'),
    [switch]$Remove,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$profileDir = Join-Path $DshHome "profiles\$Profile"
if (-not (Test-Path $profileDir)) { throw "找不到 profile 目录: $profileDir" }

$target = Join-Path $profileDir 'node_modules\dsh-file-history'
$patchFile = Join-Path $profileDir 'cordis.patch.yml'
$marker = 'dsh-file-history'
$block = @"

# ── dsh-file-history: 改前自动快照（静态常驻版）──────────────────────────
# 任何 write/edit 覆盖已存在文件前，自动把原文快照到 ~/.dsh/file-history；
# 模型侧用 file_history 工具做 list/show/restore/revert_turn。
# 配置持久化在 settings.yaml 的 file-history 段（保留天数、容量上限等）。
- insert:
    - id: dsh-file-history
      name: 'dsh-file-history'
      inject: [tools, settings, timer]
"@

if ($Remove) {
    if (Test-Path $target) {
        $backup = Join-Path $here ('.backup-remove-{0}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        New-Item -ItemType Directory -Force -Path $backup | Out-Null
        Copy-Item $target (Join-Path $backup 'dsh-file-history') -Recurse -Force
        Remove-Item $target -Recurse -Force
        Write-Host "[remove] 已移除插件副本（备份在 $backup）"
    }
    if (Test-Path $patchFile) {
        Copy-Item $patchFile "$patchFile.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')" -Force
        $lines = @(Get-Content $patchFile -Encoding utf8)
        $kept = New-Object System.Collections.Generic.List[string]
        $i = 0
        while ($i -lt $lines.Count) {
            $line = $lines[$i]
            # 只匹配「独占一行的注释」，避免碰到其它插件注释里恰好含本名字的情况
            if ($line -match "^\s*#.*$([regex]::Escape($marker)).*$") {
                # 删除本插件的登记块：紧跟的注释行 + 紧随其后的一个 - insert: 块（其缩进子行）
                $i += 1
                while ($i -lt $lines.Count -and $lines[$i] -match '^\s*#') { $i += 1 }
                if ($i -lt $lines.Count -and $lines[$i] -match '^\s*-\s*insert:') {
                    $i += 1
                    while ($i -lt $lines.Count -and ($lines[$i] -match '^\s+\S' -or $lines[$i] -match '^\s*$')) { $i += 1 }
                }
                continue
            }
            $kept.Add($line)
            $i += 1
        }
        Set-Content -Path $patchFile -Value $kept -Encoding utf8
        Write-Host '[remove] 已从 cordis.patch.yml 移除加载项（原文件已备份）'
    }
    Write-Host '[remove] 完成。重启 dsh 服务后生效；~/.dsh/file-history 里的历史快照没有被删除。'
    exit 0
}

if ((Test-Path $target) -and -not $Force) {
    Copy-Item $target (Join-Path $here ('.backup-install-{0}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))) -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $target 'lib') | Out-Null
Copy-Item (Join-Path $here 'package.json') (Join-Path $target 'package.json') -Force
Copy-Item (Join-Path $here 'lib\index.js') (Join-Path $target 'lib\index.js') -Force
Write-Host "[install] 插件已写入 $target"

if (-not (Test-Path $patchFile)) { New-Item -ItemType File -Path $patchFile | Out-Null }
$patchText = Get-Content $patchFile -Raw -Encoding utf8
if ($patchText -notmatch [regex]::Escape($marker)) {
    Copy-Item $patchFile "$patchFile.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')" -Force
    Add-Content -Path $patchFile -Value $block -Encoding utf8
    Write-Host "[install] 已在 $patchFile 登记加载项"
} else {
    Write-Host '[install] cordis.patch.yml 已登记过，跳过'
}

Write-Host ''
Write-Host '[install] 完成。注意：宿主侧 HMR 是关闭的，**必须重启 dsh 服务（或桌面版窗口）**插件才会加载。'
Write-Host '[install] 重启后跑一次：powershell -ExecutionPolicy Bypass -File after-restart-check.ps1'
