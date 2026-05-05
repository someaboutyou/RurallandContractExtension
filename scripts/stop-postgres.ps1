$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pgData = Join-Path $projectRoot "runtime\data\pgdata"
$pgCtl = Join-Path $projectRoot "runtime\windows\postgresql\bin\pg_ctl.exe"

if (-not (Test-Path $pgCtl)) {
    throw "pg_ctl not found: $pgCtl"
}

if (-not (Test-Path (Join-Path $pgData "PG_VERSION"))) {
    Write-Host "PostgreSQL data directory is not initialized."
    exit 0
}

$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    & $pgCtl "status" "-D" $pgData *> $null
    $pgStatus = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}

if ($pgStatus -ne 0) {
    Write-Host "PostgreSQL is not running."
    exit 0
}

& $pgCtl "stop" "-D" $pgData "-m" "fast"
if ($LASTEXITCODE -ne 0) {
    throw "pg_ctl stop failed."
}
