# make-icon.ps1 - Build a multi-size .ico from a source PNG for DSH Desktop.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File make-icon.ps1
#   powershell ... -File make-icon.ps1 -Source <png path> -Output <ico path>
#
# Sizes: 16, 24, 32, 48, 64, 128 (DIB payloads) and 256 (PNG payload).

param(
    [string]$Source = "C:\Users\twinblade\Desktop\dpc\favicon.png",
    [string]$Output = ""
)

Add-Type -AssemblyName System.Drawing
$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
if (-not $Output) { $Output = Join-Path $root "app.ico" }

if (-not (Test-Path $Source)) { throw "Source image not found: $Source" }

$src = [System.Drawing.Image]::FromFile($Source)
try {
    $sizes = @(16, 24, 32, 48, 64, 128, 256)
    $entries = @()   # each: @(size, byte[])

    foreach ($s in $sizes) {
        $bmp = New-Object System.Drawing.Bitmap($s, $s, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try {
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            try {
                $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $g.Clear([System.Drawing.Color]::Transparent)
                $g.DrawImage($src, 0, 0, $s, $s)
            } finally { $g.Dispose() }

            if ($s -eq 256) {
                # PNG-compressed payload (Vista+ style for the large size)
                $ms = New-Object System.IO.MemoryStream
                $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
                $data = $ms.ToArray()
                $ms.Dispose()
            } else {
                # Classic DIB payload: BITMAPINFOHEADER + BGRA (bottom-up) + AND mask.
                # NOTE: GDI+ LockBits memory is TOP-DOWN (row 0 = image top), while the
                # ICO DIB format stores rows BOTTOM-UP (first row in data = image
                # bottom). Rows must be reversed or the icon renders upside down.
                $rect = New-Object System.Drawing.Rectangle(0, 0, $s, $s)
                $bmpData = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
                $stride = $bmpData.Stride
                $pixelBytes = New-Object byte[] ($stride * $s)
                [System.Runtime.InteropServices.Marshal]::Copy($bmpData.Scan0, $pixelBytes, 0, $pixelBytes.Length)
                $bmp.UnlockBits($bmpData)

                $dib = New-Object byte[] ($stride * $s)
                for ($row = 0; $row -lt $s; $row++) {
                    # memory row $row = image row $row (top-down) -> DIB row ($s - 1 - $row)
                    [System.Array]::Copy($pixelBytes, $row * $stride, $dib, ($s - 1 - $row) * $stride, $stride)
                }

                $hdrMs = New-Object System.IO.MemoryStream
                $bw = New-Object System.IO.BinaryWriter($hdrMs)
                $bw.Write([int32]40)          # biSize
                $bw.Write([int32]$s)          # biWidth
                $bw.Write([int32]($s * 2))    # biHeight (XOR + AND)
                $bw.Write([int16]1)           # biPlanes
                $bw.Write([int16]32)          # biBitCount
                $bw.Write([int32]0)           # biCompression
                $bw.Write([int32]0)           # biSizeImage
                $bw.Write([int32]0)           # biXPelsPerMeter
                $bw.Write([int32]0)           # biYPelsPerMeter
                $bw.Write([int32]0)           # biClrUsed
                $bw.Write([int32]0)           # biClrImportant
                $bw.Flush()
                $hdrBytes = $hdrMs.ToArray()
                $bw.Dispose(); $hdrMs.Dispose()

                $maskRow = [Math]::Ceiling($s / 32.0) * 4
                $mask = New-Object byte[] ($maskRow * $s)

                $ms = New-Object System.IO.MemoryStream
                $ms.Write($hdrBytes, 0, $hdrBytes.Length)
                $ms.Write($dib, 0, $dib.Length)
                $ms.Write($mask, 0, $mask.Length)
                $data = $ms.ToArray()
                $ms.Dispose()
            }
        } finally { $bmp.Dispose() }

        $entries += , @($s, $data)
    }

    $dir = Split-Path -Parent $Output
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    $fs = [System.IO.File]::Create($Output)
    try {
        $bw = New-Object System.IO.BinaryWriter($fs)
        $bw.Write([int16]0)                  # reserved
        $bw.Write([int16]1)                  # type: icon
        $bw.Write([int16]$entries.Count)     # count
        $offset = 6 + 16 * $entries.Count
        foreach ($e in $entries) {
            $s = $e[0]; $data = $e[1]
            $dim = if ($s -ge 256) { 0 } else { $s }
            $bw.Write([byte]$dim)            # width
            $bw.Write([byte]$dim)            # height
            $bw.Write([byte]0)               # colors
            $bw.Write([byte]0)               # reserved
            $bw.Write([int16]1)              # planes
            $bw.Write([int16]32)             # bit count
            $bw.Write([int32]$data.Length)   # size
            $bw.Write([int32]$offset)        # offset
            $offset += $data.Length
        }
        foreach ($e in $entries) { $bw.Write($e[1]) }
        $bw.Flush()
        $bw.Dispose()
    } finally { $fs.Dispose() }

    Write-Output "ICO written: $Output ($((Get-Item $Output).Length) bytes, $($entries.Count) sizes)"
} finally { $src.Dispose() }
