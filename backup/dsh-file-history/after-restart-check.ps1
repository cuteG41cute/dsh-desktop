# 重启 dsh 之后的「是否已生效」体检脚本（纯读，不改任何东西）
# 用法：powershell -ExecutionPolicy Bypass -File after-restart-check.ps1
#   -Project <路径>   可选：检查某个项目的备份目录是否已经建起来（默认当前目录）

param(
    [string]$DshHome = (Join-Path $env:USERPROFILE '.dsh'),
    [string]$Profile = 'web',
    [string]$Project = (Get-Location).Path
)

$results = New-Object System.Collections.Generic.List[object]
function Check([string]$name, [bool]$pass, [string]$detail) {
    $results.Add([pscustomobject]@{ item = $name; result = $(if ($pass) { 'OK' } else { 'FAIL' }); detail = $detail })
}

$pluginDir = Join-Path $DshHome "profiles\$Profile\node_modules\dsh-file-history"
Check 'plugin installed in profile' (Test-Path (Join-Path $pluginDir 'lib\index.js')) $pluginDir

$patch = Join-Path $DshHome "profiles\$Profile\cordis.patch.yml"
$patchText = if (Test-Path $patch) { Get-Content $patch -Raw -Encoding utf8 } else { '' }
Check 'patch registers the plugin' ($patchText -match 'dsh-file-history') $patch

$fallback = Join-Path $DshHome 'file-history'
Check 'fallback dir exists (plugin apply ran)' (Test-Path $fallback) $fallback

$settings = Join-Path $DshHome 'settings.yaml'
$settingsText = if (Test-Path $settings) { Get-Content $settings -Raw -Encoding utf8 } else { '' }
Check 'settings.yaml has file-history section' ($settingsText -match '(?m)^file-history:') 'appears once the namespace is registered / first config write'

# 项目内备份目录与运行状况标志
$metaDir = Join-Path $Project '.dsh-backup\_dsh-file-history'
$statusPath = Join-Path $metaDir 'status.json'
if (Test-Path $statusPath) {
    $status = Get-Content $statusPath -Raw -Encoding utf8 | ConvertFrom-Json
    Check 'project status.json exists' $true $statusPath
    Check 'status.json has fresh timestamp' ($null -ne $status.at) ("at=" + $status.at + " snapshots=" + $status.snapshots + " lastError=" + $status.lastError)
    Write-Host ("[info] backupDir = " + $status.backupDir)
} else {
    Check 'project status.json exists' $false "$statusPath (还没有发生过覆盖写入，属正常；改一个已存在的文件后应出现)"
}

$logHits = @()
foreach ($candidate in @((Join-Path $env:TEMP 'dsh*.log'), (Join-Path $DshHome 'logs\*.log'), (Join-Path $DshHome '*.log'))) {
    $logHits += Get-ChildItem $candidate -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt (Get-Date).AddHours(-6) }
}
$armedLine = $null
foreach ($log in $logHits) {
    $hit = Select-String -Path $log.FullName -Pattern '\[file-history\] armed' -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($hit) { $armedLine = "$($log.Name): $($hit.Line.Trim())" }
}
Write-Host ('[info] recent dsh logs: ' + (($logHits | ForEach-Object { $_.FullName }) -join '; '))
if ($armedLine) { Write-Host "[info] startup log: $armedLine" } else { Write-Host '[info] no armed line in those logs (log path may differ; not fatal)' }

$results | Format-Table -AutoSize
$failed = @($results | Where-Object { $_.result -eq 'FAIL' })
Write-Host ''
$onlyExpected = @($failed | Where-Object { $_.item -like 'settings.yaml*' -or $_.item -like 'project status.json exists' })
if ($failed.Count -eq 0) {
    Write-Host '[check] ALL OK: snapshot-before-write is active. Edit an existing file, then call file_history(action="list").'
    exit 0
}
if ($failed.Count -eq $onlyExpected.Count) {
    Write-Host '[check] Loaded fine. Remaining FAILs are expected until the first config write / first overwrite.'
    exit 0
}
Write-Host '[check] Some checks failed: restart the dsh service / desktop window, then re-run this script.'
exit 1
