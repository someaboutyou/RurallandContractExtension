$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$pyinstaller = Join-Path $root 'runtime\windows\python\Scripts\pyinstaller.exe'
if (-not (Test-Path $pyinstaller)) {
    $pyinstaller = 'pyinstaller'
}

Push-Location $PSScriptRoot
try {
    & $pyinstaller --clean --noconfirm launcher.spec
}
finally {
    Pop-Location
}
