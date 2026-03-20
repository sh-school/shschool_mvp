param(
    [string]$CsvPath = "./qatar_school_ops_links.csv",
    [string]$OutDir = "./downloads"
)

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

$links = Import-Csv -Path $CsvPath

function Get-SafeName([string]$name) {
    $invalid = [System.IO.Path]::GetInvalidFileNameChars() -join ''
    $regex = New-Object System.Text.RegularExpressions.Regex("[" + [regex]::Escape($invalid) + "]")
    return $regex.Replace($name, '_')
}

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$session.UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PowerShell-Downloader"

$exts = @('.pdf','.doc','.docx','.xls','.xlsx','.zip')

foreach ($row in $links) {
    $name = Get-SafeName($row.'العنصر')
    $url  = $row.'الرابط'
    try {
        # HEAD to detect content-type if possible
        $resp = Invoke-WebRequest -Method Head -Uri $url -WebSession $session -MaximumRedirection 5 -ErrorAction Stop
        $ctype = $resp.Headers['Content-Type']
        $disp  = $resp.Headers['Content-Disposition']
        $outExt = $null
        if ($disp -and $disp -match 'filename="?([^";]+)') { $outExt = [IO.Path]::GetExtension($matches[1]) }
        if (-not $outExt) {
            try { $outExt = [IO.Path]::GetExtension(([System.Uri]$url).AbsolutePath) } catch { $outExt = '' }
        }
        if (-not $outExt) { $outExt = '.html' }
        $isDirect = $exts -contains $outExt.ToLower()
        $outFile = Join-Path $OutDir ("{0}{1}" -f $name,$outExt)
        # If not direct, try GET anyway
        Invoke-WebRequest -Uri $url -WebSession $session -MaximumRedirection 5 -OutFile $outFile -ErrorAction Stop
        Write-Host "Saved: $outFile"
    }
    catch {
        Write-Warning "Failed: $url => $($_.Exception.Message)"
    }
}
