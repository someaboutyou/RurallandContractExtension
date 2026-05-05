param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "runtime"
$stateDir = Join-Path $runtimeRoot ".state"
$installMarker = Join-Path $stateDir "installed.json"

function Require-File([string]$Path, [string]$Message) {
    if (-not (Test-Path $Path)) {
        throw $Message
    }
}

function Require-AnyFile([string[]]$Paths, [string]$Message) {
    foreach ($path in $Paths) {
        if (Test-Path $path) {
            return
        }
    }
    throw $Message
}

if ((Test-Path $installMarker) -and (-not $Force)) {
    Write-Host "Install marker already exists: $installMarker"
    Write-Host "Use -Force to re-check runtime dependencies and refresh the marker."
    exit 0
}

if (-not (Test-Path $runtimeRoot)) {
    throw "Runtime directory not found: $runtimeRoot"
}

$windowsRuntime = Join-Path $runtimeRoot "windows"
$pgBin = Join-Path $windowsRuntime "postgresql\bin"
$jdkBin = Join-Path $windowsRuntime "jdk\bin"
$geoHome = Join-Path $windowsRuntime "geoserver"
$pythonExe = Join-Path $windowsRuntime "python\python.exe"

Require-File (Join-Path $pgBin "pg_ctl.exe") "PostgreSQL not found. Expected: runtime\windows\postgresql\bin\pg_ctl.exe"
Require-File (Join-Path $pgBin "initdb.exe") "initdb not found. Expected: runtime\windows\postgresql\bin\initdb.exe"
Require-File (Join-Path $pgBin "psql.exe") "psql not found. Expected: runtime\windows\postgresql\bin\psql.exe"
Require-File (Join-Path $pgBin "createdb.exe") "createdb not found. Expected: runtime\windows\postgresql\bin\createdb.exe"
Require-File (Join-Path $pgBin "pg_isready.exe") "pg_isready not found. Expected: runtime\windows\postgresql\bin\pg_isready.exe"
Require-File (Join-Path $pgBin "pg_dump.exe") "pg_dump not found. Expected: runtime\windows\postgresql\bin\pg_dump.exe"
Require-File (Join-Path $jdkBin "java.exe") "JDK not found. Expected: runtime\windows\jdk\bin\java.exe"
Require-File $pythonExe "Python not found. Expected: runtime\windows\python\python.exe"
Require-AnyFile @(
    (Join-Path $geoHome "bin\startup.bat"),
    (Join-Path $geoHome "start.jar")
) "GeoServer startup file not found. Expected runtime\windows\geoserver\bin\startup.bat or runtime\windows\geoserver\start.jar"

& $pythonExe "-c" "import fastapi, uvicorn, sqlalchemy, psycopg, pydantic_settings, fiona" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Backend Python dependencies are missing in runtime\windows\python. Install backend\requirements.txt into the bundled runtime Python before deployment."
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeRoot "data"), (Join-Path $runtimeRoot "logs") | Out-Null

$marker = [ordered]@{
    platform = "windows"
    installedAt = (Get-Date).ToString("o")
    runtimeRoot = $runtimeRoot
}

($marker | ConvertTo-Json) | Set-Content -Path $installMarker -Encoding UTF8

Write-Host "Install check passed."
Write-Host "Marker written: $installMarker"
Write-Host "Next step: powershell -ExecutionPolicy Bypass -File .\scripts\init.ps1"
