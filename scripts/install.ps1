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

# ── 区域初始化范围（6 位国家统计局县级区划码，可选）──
# 写进 .env 后，后端首次启动 bootstrap 会从随包分发的 region_full.zip 自动
# 「缺则补」出 省->市->县->镇->村 五级区域，部署人无需手工录入任何区域。
$existingCounties = $null
$countyLine = Select-String -Path $backendEnv -Pattern '^\s*REGION_SEED_COUNTIES\s*=\s*(\S*)' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($countyLine) { $existingCounties = $countyLine.Matches[0].Groups[1].Value }
if ($null -ne $existingCounties) {
    if ($existingCounties) {
        Write-Host "Region seed counties already configured: $existingCounties - $backendEnv"
    }
} else {
    Write-Host ""
    Write-Host "=== 区域初始化（可选）==="
    Write-Host "  输入项目所在地的 6 位国家统计局行政区划代码，首次启动自动建好 省/市/县/镇/村 区域树。"
    Write-Host "  支持县级码（如 150523），也支持市级码（末两位 00，如 150500 = 初始化全市下所有旗县）。"
    Write-Host "  多个码用英文逗号分隔。直接回车 = 跳过（之后仍可在 /regions 手工建）。"
    $countyAnswer = (Read-Host "请输入 6 位县级行政区划代码" ).Trim()
    if ($countyAnswer) {
        $countyAnswer = ($countyAnswer -replace '[，、;；]', ',')
        $countyParts = @($countyAnswer.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        $badCodes = @($countyParts | Where-Object { $_ -notmatch '^\d{6}$' })
        if ($badCodes.Count -gt 0) {
            throw "行政区划码必须是 6 位数字，收到：$($badCodes -join ', ')"
        }
        $envLines = [System.Collections.Generic.List[string]]($envLines | Where-Object { $_ -notmatch '^\s*REGION_SEED_COUNTIES\s*=' })
        $envLines.Add("REGION_SEED_COUNTIES=$($countyParts -join ',')") | Out-Null
        Write-Host "Region seed counties: $($countyParts -join ',') -> $backendEnv"
    }
}
# ⛔ 不能用 Set-Content -Encoding UTF8：PS 5.1 会写 BOM，pydantic-settings 按
# utf-8 读时首键名变 "\ufeffapp_name" 报 extra_forbidden。必须无 BOM UTF-8。
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($backendEnv, [string[]]$envLines, $utf8NoBom)
Write-Host "Target SRID: $TargetSrid (CGCS2000 / 3-degree Gauss-Kruger zone $(Get-SridZone $TargetSrid)) -> $backendEnv"

# ── JWT 密钥（安全审计 H1）：缺失或仍为公开默认值时生成随机密钥 ──
# 后端启动时检测到公开默认密钥会拒绝启动（app/core/config.py fail-fast）。
$jwtSentinel = "replace-this-in-production"
$jwtLine = $envLines | Where-Object { $_ -match '^\s*JWT_SECRET_KEY\s*=' } | Select-Object -First 1
$needNewJwt = $true
if ($jwtLine) {
    $existingJwt = ($jwtLine -split '=', 2)[1].Trim()
    if ($existingJwt -and $existingJwt -ne $jwtSentinel) {
        $needNewJwt = $false
        Write-Host "JWT secret already configured in $backendEnv"
    }
}
if ($needNewJwt) {
    $jwtBytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($jwtBytes) } finally { $rng.Dispose() }
    $jwtSecret = [Convert]::ToBase64String($jwtBytes)
    $envLines = [System.Collections.Generic.List[string]]($envLines | Where-Object { $_ -notmatch '^\s*JWT_SECRET_KEY\s*=' })
    $envLines.Add("JWT_SECRET_KEY=$jwtSecret") | Out-Null
    # ⛔ 不能用 Set-Content -Encoding UTF8：PS 5.1 会写 BOM，pydantic-settings 按
    # utf-8 读时首键名变 "\ufeffapp_name" 报 extra_forbidden。必须无 BOM UTF-8。
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($backendEnv, [string[]]$envLines, $utf8NoBom)
    Write-Host "Generated random JWT_SECRET_KEY -> $backendEnv"
}

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
