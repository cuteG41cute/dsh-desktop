$root = 'C:\Users\User\AppData\Local\dsh-manager\instances'
$p = Join-Path $root 'dsh-a'
Write-Output ('exists=' + (Test-Path $p))
try {
    Remove-Item $p -Recurse -Force -ErrorAction Stop
    Write-Output 'plain Remove-Item ok'
} catch {
    Write-Output ('plain FAILED: ' + $_.Exception.Message)
}
if (Test-Path $p) {
    $long = '\\?\' + $p
    try {
        # 统计超长路径文件数
        $deep = 0
        Get-ChildItem $long -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.FullName.Length -gt 260) { $deep++ }
        }
        Write-Output ('files_over_260=' + $deep)
        cmd /c rd /s /q "$long" 2>&1 | Out-Null
    } catch { Write-Output ('rd failed: ' + $_.Exception.Message) }
}
Write-Output ('exists_after=' + (Test-Path $p))
