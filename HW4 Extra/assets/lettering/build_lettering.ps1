param(
    [string]$FontPath = (Join-Path $PSScriptRoot 'fonts\CinzelDecorative-Bold.ttf'),
    [ValidateSet('Regular', 'Bold')][string]$FontStyle = 'Bold',
    [ValidateRange(0, .5)][double]$TrackingEm = .14,
    [ValidatePattern('^[a-zA-Z0-9_]+$')][string]$OutputName = 'house_names_cinzel',
    [string]$SourceUrl = 'https://github.com/google/fonts/tree/main/ofl/cinzeldecorative'
)

# Optional asset builder. The application loads the PNG and needs no font installed.
Add-Type -AssemblyName System.Drawing
$fontCollection = [System.Drawing.Text.PrivateFontCollection]::new()
$fontCollection.AddFontFile($FontPath)
$bannerFont = [System.Drawing.Font]::new($fontCollection.Families[0], 224,
    [System.Enum]::Parse([System.Drawing.FontStyle], $FontStyle), [System.Drawing.GraphicsUnit]::Pixel)
$bitmap = [System.Drawing.Bitmap]::new(2048, 2048,
    [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$format = [System.Drawing.StringFormat]::GenericTypographic.Clone()
$brush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)

try {
    $graphics.Clear([System.Drawing.Color]::Transparent)
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $format.FormatFlags = [System.Drawing.StringFormatFlags]::NoWrap -bor [System.Drawing.StringFormatFlags]::NoClip
    $names = @('GRYFFINDOR', 'SLYTHERIN', 'RAVENCLAW', 'HUFFLEPUFF')
    $tracking = $bannerFont.Size * $TrackingEm
    $lineHeight = $bannerFont.GetHeight($graphics)
    # Add tracking to glyph advances, then rotate the complete word clockwise.
    $longest = 0
    foreach ($name in $names) {
        $wordWidth = $tracking * ($name.Length - 1)
        foreach ($letter in $name.ToCharArray()) {
            $wordWidth += $graphics.MeasureString([string]$letter, $bannerFont, 4096, $format).Width
        }
        $longest = [Math]::Max($longest, $wordWidth)
    }
    $commonScale = [Math]::Min(1856 / $longest, 416 / $lineHeight)
    for ($column = 0; $column -lt $names.Count; $column++) {
        $name = $names[$column]
        $state = $graphics.Save()
        $graphics.TranslateTransform($column * 512 + 256, 96)
        $graphics.RotateTransform(90)
        $graphics.ScaleTransform($commonScale, $commonScale)
        $cursor = 0
        foreach ($letter in $name.ToCharArray()) {
            $glyph = [string]$letter
            $graphics.DrawString($glyph, $bannerFont, $brush,
                [System.Drawing.PointF]::new($cursor, -$lineHeight / 2), $format)
            $cursor += $graphics.MeasureString($glyph, $bannerFont, 4096, $format).Width + $tracking
        }
        $graphics.Restore($state)
    }
    $bitmap.Save((Join-Path $PSScriptRoot ($OutputName + '.png')), [System.Drawing.Imaging.ImageFormat]::Png)
    $metadata = @{
        font = $bannerFont.Name
        style = $FontStyle
        source = $SourceUrl
        tracking_em = $TrackingEm
        size = @(2048, 2048)
        columns = $names
        layout = 'Whole words rotated 90 degrees clockwise, read from top to bottom'
        rotation_degrees = 90
    } | ConvertTo-Json -Depth 3
    $metadataName = if ($OutputName -eq 'house_names') { 'metadata.json' } else { $OutputName + '.json' }
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot $metadataName), $metadata,
        [System.Text.UTF8Encoding]::new($false))
}
finally {
    $brush.Dispose()
    $format.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
    $bannerFont.Dispose()
    $fontCollection.Dispose()
}
