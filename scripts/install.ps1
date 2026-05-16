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
$redisHome = Join-Path $windowsRuntime "redis"
$pythonExe = Join-Path $windowsRuntime "python\python.exe"
$pgLib = Join-Path $windowsRuntime "postgresql\lib"

Require-File (Join-Path $pgBin "pg_ctl.exe") "PostgreSQL not found. Expected: runtime\windows\postgresql\bin\pg_ctl.exe"
Require-File (Join-Path $pgBin "initdb.exe") "initdb not found. Expected: runtime\windows\postgresql\bin\initdb.exe"
Require-File (Join-Path $pgBin "psql.exe") "psql not found. Expected: runtime\windows\postgresql\bin\psql.exe"
Require-File (Join-Path $pgBin "createdb.exe") "createdb not found. Expected: runtime\windows\postgresql\bin\createdb.exe"
Require-File (Join-Path $pgBin "pg_isready.exe") "pg_isready not found. Expected: runtime\windows\postgresql\bin\pg_isready.exe"
Require-File (Join-Path $pgBin "pg_dump.exe") "pg_dump not found. Expected: runtime\windows\postgresql\bin\pg_dump.exe"
Require-File (Join-Path $pgBin "libgeos_c.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libgeos_c.dll"
Require-File (Join-Path $pgBin "libproj_8_2.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libproj_8_2.dll"
Require-File (Join-Path $pgBin "libprotobuf-c-1.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libprotobuf-c-1.dll"
Require-File (Join-Path $pgBin "libstdc++-6.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libstdc++-6.dll"
Require-File (Join-Path $pgBin "libxml2-2.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libxml2-2.dll"
Require-File (Join-Path $pgBin "libgdal-34.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libgdal-34.dll"
Require-File (Join-Path $pgBin "libgeos.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libgeos.dll"
Require-File (Join-Path $pgBin "libSFCGAL.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libSFCGAL.dll"
Require-File (Join-Path $pgBin "libsqlite3-0.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libsqlite3-0.dll"
Require-File (Join-Path $pgBin "libtiff-6.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libtiff-6.dll"
Require-File (Join-Path $pgBin "libexpat-1.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libexpat-1.dll"
Require-File (Join-Path $pgBin "libgcc_s_seh-1.dll") "PostGIS dependency not found. Expected: runtime\windows\postgresql\bin\libgcc_s_seh-1.dll"
Require-File (Join-Path $jdkBin "java.exe") "JDK not found. Expected: runtime\windows\jdk\bin\java.exe"
Require-File (Join-Path $redisHome "redis-server.exe") "Redis server not found. Expected: runtime\windows\redis\redis-server.exe"
Require-File (Join-Path $redisHome "redis-cli.exe") "Redis CLI not found. Expected: runtime\windows\redis\redis-cli.exe"
Require-File $pythonExe "Python not found. Expected: runtime\windows\python\python.exe"
Require-AnyFile @(
    (Join-Path $geoHome "bin\startup.bat"),
    (Join-Path $geoHome "start.jar")
) "GeoServer startup file not found. Expected runtime\windows\geoserver\bin\startup.bat or runtime\windows\geoserver\start.jar"

& $pythonExe "-c" "import ctypes, os, sys; os.add_dll_directory(r'$pgBin'); ctypes.CDLL(r'$(Join-Path $pgLib "postgis-3.dll")'); ctypes.CDLL(r'$(Join-Path $pgLib "postgis_topology-3.dll")')"
if ($LASTEXITCODE -ne 0) {
    throw "PostGIS DLL load check failed. Ensure runtime\windows\postgresql\bin contains all PostGIS dependency DLLs."
}

& $pythonExe "-c" "import fastapi, uvicorn, sqlalchemy, psycopg, pydantic_settings, fiona, redis" *> $null
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
