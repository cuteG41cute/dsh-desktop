# 摸清本机这几个 DSH 安装到底是什么、谁在用、删了会影响什么（ASCII only）。
$ErrorActionPreference = 'SilentlyContinue'

function Show-Dir($label, $path) {
    if (-not (Test-Path $path)) { Write-Host ("{0,-22} {1}  (不存在)" -f $label, $path); return }
    $files = Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue
    $mb = [math]::Round((($files | Measure-Object Length -Sum).Sum / 1MB), 1)
    $newest = ($files | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
    Write-Host ("{0,-22} {1}" -f $label, $path)
    Write-Host ("{0,-22} 大小 {1} MB, 文件 {2}, 最近修改 {3}" -f '', $mb, $files.Count, $newest)
}

Write-Host "== 正在跑的进程"
$conn = Get-NetTCPConnection -State Listen -LocalPort 3080 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)"
    Write-Host ("  PID {0}  {1}" -f $conn.OwningProcess, $proc.CommandLine)
}

Write-Host ""
Write-Host "== 三个安装"
$npx = Join-Path $env:LOCALAPPDATA 'npm-cache\_npx'
Get-ChildItem $npx -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $entry = Join-Path $_.FullName 'node_modules\@deepseek-ai\dsh'
    if (Test-Path $entry) {
        Show-Dir ('npx ' + $_.Name.Substring(0, [Math]::Min(12, $_.Name.Length))) $entry
    }
}
$pi = Join-Path $env:LOCALAPPDATA 'pi-node\current'
Show-Dir 'pi-node' $pi

Write-Host ""
Write-Host "== pi-node 里除了 dsh 还有什么"
Get-ChildItem $pi -ErrorAction SilentlyContinue | Select-Object -First 12 | ForEach-Object { Write-Host ("  " + $_.Name) }

Write-Host ""
Write-Host "== 用户数据在哪（删安装不影响这里）"
$dshHome = Join-Path $env:USERPROFILE '.dsh'
if (Test-Path $dshHome) {
    $s = (Get-ChildItem $dshHome -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum)
    Write-Host ("  {0}  {1} MB / {2} 文件" -f $dshHome, [math]::Round($s.Sum / 1MB, 1), $s.Count)
    Get-ChildItem $dshHome | Select-Object -First 8 | ForEach-Object { Write-Host ("    " + $_.Name) }
}

Write-Host ""
Write-Host "== 哪些快捷方式/任务引用了这些路径"
$hits = @()
$targets = @($pi, $npx)
foreach ($dir in @((Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu'), (Join-Path $env:USERPROFILE 'Desktop'))) {
    Get-ChildItem $dir -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {
        $sh = New-Object -ComObject WScript.Shell
        $lnk = $sh.CreateShortcut($_.FullName)
        foreach ($t in $targets) {
            if ($lnk.TargetPath -like ($t + '*')) { $hits += ("{0} -> {1}" -f $_.FullName, $lnk.TargetPath) }
        }
    }
}
if ($hits.Count -eq 0) { Write-Host '  （没有快捷方式直接指向它们）' } else { $hits | ForEach-Object { Write-Host ("  " + $_) } }
