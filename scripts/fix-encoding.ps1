$target = Join-Path $PSScriptRoot "start-geoserver.ps1"
$content = [System.IO.File]::ReadAllText($target, [System.Text.Encoding]::UTF8)
$utf8Bom = [System.Text.UTF8Encoding]::new($true)
[System.IO.File]::WriteAllText($target, $content, $utf8Bom)
Write-Host "Fixed encoding: $target"
