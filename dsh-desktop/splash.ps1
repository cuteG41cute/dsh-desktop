# ============================================================================
# 启动画面（splash screen）
#   与项目宣传图同色系的粉彩渐变 + 底部细进度条，供 launcher.ps1 调用：
#       $script:SplashForm = New-SplashScreen
#       Update-Splash -Percent 40 -Status "正在启动本地服务…"
#       Close-Splash
#   单独自检（不启动服务，只把画面渲染出来并存成 PNG）：
#       $env:DSH_SPLASH_DUMP="$env:TEMP\splash-demo.png"
#       powershell -NoProfile -ExecutionPolicy Bypass -File splash.ps1 -Demo
# ============================================================================
[CmdletBinding()]
param(
    [switch]$Demo,
    [switch]$Run,
    [int]$DemoMs = 2600,
    [int]$CapSeconds = 45,
    [int]$MinMs = 1200,
    [int]$ParentPid = 0,
    [string]$WatchProcess = 'DSH Desktop',
    [string]$DumpPath = $env:DSH_SPLASH_DUMP
)

$script:SplashForm = $null
$script:SplashPercent = 0
$script:SplashStatus = '正在准备…'
$script:SplashIcon = $null
$script:SplashDump = $DumpPath
if (-not $script:SplashExePath) { $script:SplashExePath = Join-Path $PSScriptRoot "DSH Desktop.exe" }

function New-SplashScreen {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        [System.Windows.Forms.Application]::EnableVisualStyles()
        $form = New-Object System.Windows.Forms.Form
        $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
        $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
        $form.ClientSize = New-Object System.Drawing.Size(560, 300)
        $form.ShowInTaskbar = $true
        $form.TopMost = $true
        $form.Text = "DeepSeek Harness 桌面版"
        $form.BackColor = [System.Drawing.Color]::FromArgb(250, 252, 247)
        $gp = New-Object System.Drawing.Drawing2D.GraphicsPath
        $r = 20; $wd = 560; $ht = 300
        $gp.AddArc(0, 0, $r, $r, 180, 90); $gp.AddArc($wd - $r, 0, $r, $r, 270, 90)
        $gp.AddArc($wd - $r, $ht - $r, $r, $r, 0, 90); $gp.AddArc(0, $ht - $r, $r, $r, 90, 90)
        $gp.CloseFigure(); $form.Region = New-Object System.Drawing.Region($gp)
        # 关键：双缓冲 + AllPaintingInWmPaint，否则每次重绘都会先擦背景再画，整幅画面闪一下
        try {
            $flags = [System.Reflection.BindingFlags]'Instance,NonPublic'
            $dbProp = $form.GetType().GetProperty('DoubleBuffered', $flags)
            if ($dbProp) { $dbProp.SetValue($form, $true) }
            $setStyle = [System.Windows.Forms.Control].GetMethod('SetStyle', $flags)
            if ($setStyle) {
                $style = [System.Windows.Forms.ControlStyles]::AllPaintingInWmPaint -bor [System.Windows.Forms.ControlStyles]::OptimizedDoubleBuffer -bor [System.Windows.Forms.ControlStyles]::UserPaint
                $setStyle.Invoke($form, @($style, $true)) | Out-Null
            }
            # UpdateStyles 是受保护方法，SetStyle 已即时生效，这里不需要再调用
        } catch { }
        try {
            if (Test-Path $script:SplashExePath) {
                $script:SplashIcon = [System.Drawing.Icon]::ExtractAssociatedIcon($script:SplashExePath)
            }
        } catch {}

        $form.Add_Paint({
            param($s, $e)
            $g = $e.Graphics
            $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
            $W = $s.ClientSize.Width; $H = $s.ClientSize.Height
            $rect = New-Object System.Drawing.Rectangle(0, 0, $W, $H)
            $bg = New-Object System.Drawing.Drawing2D.LinearGradientBrush($rect, [System.Drawing.Color]::FromArgb(214, 245, 246), [System.Drawing.Color]::FromArgb(253, 251, 240), 30.0)
            $g.FillRectangle($bg, $rect)
            $pink = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(70, 236, 176, 195))
            $g.FillEllipse($pink, ($W - 210), -120, 320, 250)
            $teal = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(45, 20, 184, 166))
            $g.FillEllipse($teal, -130, ($H - 180), 270, 270)
            if ($script:SplashIcon) {
                $iconRect = New-Object System.Drawing.Rectangle(40, 44, 44, 44)
                $g.DrawIcon($script:SplashIcon, $iconRect)
            }
            $fTitle = New-Object System.Drawing.Font("Microsoft YaHei UI", 17, [System.Drawing.FontStyle]::Bold)
            $fSub = New-Object System.Drawing.Font("Microsoft YaHei UI", 10)
            $fSmall = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)
            $cInk = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(11, 18, 32))
            $cAccent = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(15, 143, 138))
            $cMuted = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(91, 107, 127))
            $g.DrawString("DeepSeek Harness", $fTitle, $cInk, 40, 102)
            $g.DrawString("桌面版", $fTitle, $cAccent, 40, 140)
            $g.DrawString("把 WebUI 变成真正的桌面应用 · 无浏览器 · 无控制台", $fSub, $cMuted, 42, 186)

            $barX = 40; $barY = 236; $barW = $W - 80; $barH = 8
            $trackPath = New-Object System.Drawing.Drawing2D.GraphicsPath
            $trackPath.AddArc($barX, $barY, $barH, $barH, 90, 180)
            $trackPath.AddArc(($barX + $barW - $barH), $barY, $barH, $barH, 270, 180)
            $trackPath.CloseFigure()
            $trackBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(48, 120, 140, 165))
            $g.FillPath($trackBrush, $trackPath)
            $pct = [Math]::Max(0, [Math]::Min(100, [int]$script:SplashPercent))
            if ($pct -gt 0) {
                $fillW = [Math]::Max($barH, [int]($barW * $pct / 100))
                $fillPath = New-Object System.Drawing.Drawing2D.GraphicsPath
                $fillPath.AddArc($barX, $barY, $barH, $barH, 90, 180)
                $fillPath.AddArc(($barX + $fillW - $barH), $barY, $barH, $barH, 270, 180)
                $fillPath.CloseFigure()
                $fillRect = New-Object System.Drawing.Rectangle($barX, $barY, $fillW, $barH)
                $fillBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($fillRect, [System.Drawing.Color]::FromArgb(20, 184, 166), [System.Drawing.Color]::FromArgb(77, 107, 254), 0.0)
                $g.FillPath($fillBrush, $fillPath)
            }
            $pctText = [string]$pct + "%"
            $g.DrawString($pctText, $fSmall, $cMuted, ($W - 74), ($barY - 22))
            $g.DrawString([string]$script:SplashStatus, $fSmall, $cMuted, 40, ($barY + 18))
        })

        $form.Show()
        [System.Windows.Forms.Application]::DoEvents()
        return $form
    } catch {
        return $null
    }
}

function Update-Splash {
    param([int]$Percent, [string]$Status)
    if (-not $script:SplashForm) { return }
    try {
        if ($Percent -gt $script:SplashPercent) { $script:SplashPercent = $Percent }
        if ($Status) { $script:SplashStatus = $Status }
        $script:SplashForm.Invalidate()
        $script:SplashForm.Update()
        [System.Windows.Forms.Application]::DoEvents()
        if ($script:SplashDump) {
            $bmp = New-Object System.Drawing.Bitmap($script:SplashForm.ClientSize.Width, $script:SplashForm.ClientSize.Height)
            $rectAll = New-Object System.Drawing.Rectangle(0, 0, $bmp.Width, $bmp.Height)
            $script:SplashForm.DrawToBitmap($bmp, $rectAll)
            $bmp.Save($script:SplashDump, [System.Drawing.Imaging.ImageFormat]::Png)
            $bmp.Dispose()
        }
    } catch {}
}

function Close-Splash {
    if (-not $script:SplashForm) { return }
    try { $script:SplashForm.Close(); $script:SplashForm.Dispose() } catch {}
    $script:SplashForm = $null
}

# ---------------------------------------------------------------------------
# 独立进程模式：launcher.ps1 只用 Start-Process 拉起它，不再需要任何流程改动。
# 自己按时间推进进度条，并在"桌面窗口出现"时填满、收尾、退出。
# ---------------------------------------------------------------------------
if ($Run) {
    # 已经在运行（存在带主窗口的进程）→ 本次双击只是唤起旧窗口，不该闪一下启动画面。
    # launcher.ps1 也有一道同样的门，这里再兜一次底（直接调用本脚本时同样成立）。
    try {
        $already = @(Get-Process -Name $WatchProcess -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 })
        if ($already.Count -gt 0) { exit 0 }
    } catch { }
    $script:SplashCapSeconds = $CapSeconds
    $script:SplashWatch = $WatchProcess
    $script:SplashParent = $ParentPid
    $script:SplashMinMs = $MinMs
    $script:SplashForm = New-SplashScreen
    if (-not $script:SplashForm) { exit 1 }
    $script:SplashPercent = 4
    $script:SplashStatus = '正在准备启动…'
    $script:SplashT0 = Get-Date
    $script:SplashTicks = 0
    $script:SplashClosing = $false
    $script:SplashPaintedPct = -1
    $script:SplashPaintedMsg = ""
    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = 120

    $timer.Add_Tick({
        $elapsed = ((Get-Date) - $script:SplashT0).TotalMilliseconds
        $script:SplashTicks++
        if ($script:SplashPercent -lt 92) {
            $target = [int](6 + [Math]::Min(86, $elapsed / 85))
            if ($target -gt $script:SplashPercent) { $script:SplashPercent = $target }
        }
        if ($elapsed -lt 1600) { $script:SplashStatus = '正在准备启动…' }
        elseif ($elapsed -lt 5000) { $script:SplashStatus = '正在启动本地服务…' }
        else { $script:SplashStatus = '正在加载界面…' }
        if (-not $script:SplashClosing -and ($script:SplashTicks % 4) -eq 0) {
            $win = @(Get-Process -Name $script:SplashWatch -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 })
            if ($win.Count -gt 0 -and $elapsed -gt $script:SplashMinMs) {
                $script:SplashPercent = 100
                $script:SplashStatus = '启动完成'
                $script:SplashClosing = $true
                $timer.Stop()
                $script:SplashPaintedPct = -1
                $script:SplashForm.Invalidate(); $script:SplashForm.Update()
                Start-Sleep -Milliseconds 420
                $script:SplashForm.Close()
                return
            }
        }
        if (-not $script:SplashClosing -and $script:SplashParent -gt 0) {
            if (-not (Get-Process -Id $script:SplashParent -ErrorAction SilentlyContinue)) {
                $script:SplashClosing = $true
                $timer.Stop()
                $script:SplashForm.Close()
                return
            }
        }
        if (-not $script:SplashClosing -and $elapsed -gt ($script:SplashCapSeconds * 1000)) {
            $script:SplashClosing = $true
            $timer.Stop()
            $script:SplashForm.Close()
            return
        }
        if ($script:SplashPercent -ne $script:SplashPaintedPct -or $script:SplashStatus -ne $script:SplashPaintedMsg) {
            $script:SplashPaintedPct = $script:SplashPercent
            $script:SplashPaintedMsg = $script:SplashStatus
            $script:SplashForm.Invalidate()
            $script:SplashForm.Update()
            if ($script:SplashDump) {
                Add-Content -Path ($script:SplashDump + '.ticks.log') -Value ((Get-Date -Format 'HH:mm:ss.fff') + '  ' + [string]$script:SplashPercent + '%  ' + [string]$script:SplashStatus)
            }
        }
        if ($script:SplashDump) {
            $bmp = New-Object System.Drawing.Bitmap(560, 300)
            $script:SplashForm.DrawToBitmap($bmp, (New-Object System.Drawing.Rectangle(0, 0, 560, 300)))
            $bmp.Save($script:SplashDump, [System.Drawing.Imaging.ImageFormat]::Png)
            $bmp.Dispose()
        }
    })
    $timer.Start()
    [System.Windows.Forms.Application]::Run($script:SplashForm)
    exit 0
}

# ---------------------------------------------------------------------------
# 自检模式：不启动服务，只把各个进度档渲染出来（配合 DSH_SPLASH_DUMP 存图）
# ---------------------------------------------------------------------------
if ($Demo) {
    $script:SplashForm = New-SplashScreen
    if (-not $script:SplashForm) { Write-Output "启动画面创建失败"; exit 1 }
    $steps = @(
        @(10, '正在准备启动…'),
        @(18, '正在检查服务状态…'),
        @(32, '正在启动本地服务…'),
        @(58, '正在启动本地服务…'),
        @(78, '正在获取访问凭据…'),
        @(90, '正在打开桌面窗口…'),
        @(100, '启动完成')
    )
    foreach ($s in $steps) {
        Update-Splash -Percent $s[0] -Status $s[1]
        Start-Sleep -Milliseconds ([Math]::Max(120, [int]($DemoMs / $steps.Count)))
    }
    if ($script:SplashDump) { Write-Output ("已渲染启动画面: {0}" -f $script:SplashDump) }
    Start-Sleep -Milliseconds 300
    Close-Splash
    Write-Output "启动画面自检完成（无异常）"
}