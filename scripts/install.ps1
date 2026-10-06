param(
    [switch]$Force,
    # 目标坐标系 EPSG 代码（CGCS2000 3°高斯-克吕格投影，带号 25-45，EPSG 4513-4533）。
    # 0 = 交互式选择（默认）。跳过交互可直接传：.\install.ps1 -TargetSrid 4527
    [int]$TargetSrid = 0
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "runtime"
$stateDir = Join-Path $runtimeRoot ".state"
$installMarker = Join-Path $stateDir "installed.json"
$backendEnv = Join-Path $projectRoot "backend\.env"
$backendEnvExample = Join-Path $projectRoot "backend\.env.example"

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

# ── 目标坐标系选择（必须在数据库初始化之前确定，写入后首次启动即固化，不可再改）──
# 3°高斯-克吕格投影：EPSG = 4488 + 带号（25 带 = 4513 … 45 带 = 4533），默认 39 带（4527）。
function Get-SridZone([int]$Epsg) { return $Epsg - 4488 }

if ($TargetSrid -eq 0) {
    # backend/.env 里已经配过就不再问（幂等重装）
    $existingSrid = $null
    if (Test-Path $backendEnv) {
        $line = Select-String -Path $backendEnv -Pattern '^\s*TARGET_SRID\s*=\s*(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($line) { $existingSrid = [int]$line.Matches[0].Groups[1].Value }
    }
    if ($existingSrid) {
        $TargetSrid = $existingSrid
        Write-Host "Target SRID already configured: $TargetSrid (zone $(Get-SridZone $TargetSrid)) - $backendEnv"
    } else {
        Write-Host ""
        Write-Host "=== 选择项目目标坐标系（CGCS2000 / 3 度高斯-克吕格投影）==="
        Write-Host "  本项目数据的投影带由部署地经度决定，初始化后不可更改。"
        Write-Host "  常用带号：35 带(109.5E) 36 带(112.5E) 37 带(115.5E) 38 带(118.5E)... 视项目所在县经度而定。"
        Write-Host "  直接回车 = 默认 39 带（EPSG:4527，中央子午线 117 度）。"
        $answer = Read-Host "请输入 3 度带带号 (25-45) 或 EPSG 代码 (4513-4533)"
        $answer = $answer.Trim()
        if ([string]::IsNullOrEmpty($answer)) {
            $TargetSrid = 4527
        } elseif ($answer -match '^\d+$' -and [int]$answer -le 45 -and [int]$answer -ge 25) {
            $TargetSrid = 4488 + [int]$answer
        } elseif ($answer -match '^\d+$') {
            $TargetSrid = [int]$answer
        } else {
            throw "无效输入：'$answer'。请输入 25-45 的带号或 4513-4533 的 EPSG 代码。"
        }
    }
}

if ($TargetSrid -lt 4513 -or $TargetSrid -gt 4533) {
    throw "目标坐标系 EPSG:$TargetSrid 不在支持范围（CGCS2000 3 度高斯-克吕格投影 4513-4533）。"
}

if (-not (Test-Path $backendEnv)) {
    if (Test-Path $backendEnvExample) {
        Copy-Item $backendEnvExample $backendEnv
    } else {
        New-Item -ItemType File -Path $backendEnv | Out-Null
    }
}
$envLines = [System.Collections.Generic.List[string]](Get-Content $backendEnv)
$envLines = [System.Collections.Generic.List[string]]($envLines | Where-Object { $_ -notmatch '^\s*TARGET_SRID\s*=' })
$envLines.Add("TARGET_SRID=$TargetSrid") | Out-Null
$envLines | Set-Content -Path $backendEnv -Encoding UTF8
Write-Host "Target SRID: $TargetSrid (CGCS2000 / 3-degree Gauss-Kruger zone $(Get-SridZone $TargetSrid)) -> $backendEnv"

$marker = [ordered]@{
    platform = "windows"
    installedAt = (Get-Date).ToString("o")
    runtimeRoot = $runtimeRoot
    targetSrid = $TargetSrid
}

($marker | ConvertTo-Json) | Set-Content -Path $installMarker -Encoding UTF8

Write-Host "Install check passed."
Write-Host "Marker written: $installMarker"
Write-Host "Next step: powershell -ExecutionPolicy Bypass -File .\scripts\init.ps1"
