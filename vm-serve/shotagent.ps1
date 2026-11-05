$ErrorActionPreference = 'Continue'
$req = 'C:\Users\User\shot.req'
$done = 'C:\Users\User\shot.done'
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
while ($true) {
    if (Test-Path $req) {
        $name = ''
        try { $name = (Get-Content $req -Raw -ErrorAction SilentlyContinue).Trim() } catch {}
        Remove-Item $req -Force -ErrorAction SilentlyContinue
        if ($name) {
            try {
                $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
                $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
                $g = [System.Drawing.Graphics]::FromImage($bmp)
                $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
                $bmp.Save(('C:\Users\User\' + $name + '.png'), [System.Drawing.Imaging.ImageFormat]::Png)
                $g.Dispose(); $bmp.Dispose()
                Set-Content $done $name -Encoding ASCII
            } catch {
                Set-Content $done ('ERR ' + $_.Exception.Message) -Encoding UTF8
            }
        }
    }
    Start-Sleep -Milliseconds 700
}
