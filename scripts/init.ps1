param(
    [int]$DbPort = 15432,
    [string]$DbName = "erlunyanbao",
    [string]$DbUser = "RurallandContractExtension",
    [string]$DbPassword = "RurallandContractExtension",
    [string]$SchemaSourceHost = "127.0.0.1",
    [int]$SchemaSourcePort = 5432,
    [string]$SchemaSourceDbName = "erlunyanbao",
    [string]$SchemaSourceUser = "RurallandContractExtension",
    [string]$SchemaSourcePassword = "RurallandContractExtension",
    [string]$SchemaName = "public",
    [switch]$ImportSchemaFromSource,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "runtime"
$stateDir = Join-Path $runtimeRoot ".state"
$installMarker = Join-Path $stateDir "installed.json"
$initMarker = Join-Path $stateDir "initialized.json"
$runtimeEnvFile = Join-Path $stateDir "runtime.env"
$pgBin = Join-Path $runtimeRoot "windows\postgresql\bin"
$psql = Join-Path $pgBin "psql.exe"
$pgDump = Join-Path $pgBin "pg_dump.exe"
$logDir = Join-Path $runtimeRoot "logs"
$backendPath = Join-Path $projectRoot "backend"
$portablePython = Join-Path $runtimeRoot "windows\python\python.exe"
$sqlInitFile = Join-Path $PSScriptRoot "sql\init-postgis-schema.sql"

function Get-PythonExecutable {
    if (Test-Path $portablePython) {
        return $portablePython
    }
    return $null
}

function Test-BackendPythonDependencies([string]$PythonExe) {
    & $PythonExe "-c" "import fastapi, sqlalchemy, psycopg, pydantic_settings, fiona" *> $null
    return $LASTEXITCODE -eq 0
}

function Ensure-BackendPythonEnvironment {
    $pythonExe = Get-PythonExecutable
    if ([string]::IsNullOrWhiteSpace($pythonExe) -or -not (Test-Path $pythonExe)) {
        throw "Python not found. Put portable Python under runtime\windows\python."
    }

    if (Test-BackendPythonDependencies $pythonExe) {
        return $pythonExe
    }

    throw "Backend Python dependencies are missing in runtime\windows\python. Install backend\requirements.txt into the bundled runtime Python before deployment."
}

function Invoke-PsqlScalar(
    [string]$HostName,
    [int]$Port,
    [string]$Database,
    [string]$User,
    [string]$Password,
    [string]$Sql
) {
    $previousPassword = $env:PGPASSWORD
    $env:PGPASSWORD = $Password
    try {
        $result = & $psql "-h" $HostName "-p" "$Port" "-U" $User "-d" $Database "-tAc" $Sql
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return (($result | Out-String).Trim())
    } finally {
        $env:PGPASSWORD = $previousPassword
    }
}

function Test-DatabaseAvailable(
    [string]$HostName,
    [int]$Port,
    [string]$Database,
    [string]$User,
    [string]$Password
) {
    $value = Invoke-PsqlScalar $HostName $Port $Database $User $Password "SELECT 1"
    return $value -eq "1"
}

function Get-UserTableCount(
    [string]$HostName,
    [int]$Port,
    [string]$Database,
    [string]$User,
    [string]$Password,
    [string]$Schema
) {
    $schemaLiteral = $Schema.Replace("'", "''")
    $sql = @"
SELECT count(*)
FROM information_schema.tables
WHERE table_schema = '$schemaLiteral'
  AND table_type = 'BASE TABLE'
  AND table_name NOT IN ('spatial_ref_sys');
"@
    $value = Invoke-PsqlScalar $HostName $Port $Database $User $Password $sql
    if ([string]::IsNullOrWhiteSpace($value)) {
        return 0
    }
    return [int]$value
}

function Import-PublicSchemaFromExistingDatabase(
    [string]$SourceHost,
    [int]$SourcePort,
    [string]$SourceDatabase,
    [string]$SourceUser,
    [string]$SourcePassword,
    [string]$TargetHost,
    [int]$TargetPort,
    [string]$TargetDatabase,
    [string]$TargetUser,
    [string]$TargetPassword,
    [string]$Schema
) {
    if ($SourceHost -eq $TargetHost -and $SourcePort -eq $TargetPort -and $SourceDatabase -eq $TargetDatabase) {
        Write-Host "Schema source and target are the same database. Schema import skipped."
        return
    }

    if (-not (Test-DatabaseAvailable $SourceHost $SourcePort $SourceDatabase $SourceUser $SourcePassword)) {
        Write-Host "Schema source database is not available: ${SourceHost}:$SourcePort/$SourceDatabase. Schema import skipped."
        return
    }

    $targetTableCount = Get-UserTableCount $TargetHost $TargetPort $TargetDatabase $TargetUser $TargetPassword $Schema
    if ($targetTableCount -gt 0) {
        Write-Host "Target schema $Schema already has $targetTableCount user table(s). Schema import skipped."
        return
    }

    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $dumpFile = Join-Path $logDir "schema-$Schema.sql"

    Write-Host "Importing table structure from ${SourceHost}:$SourcePort/$SourceDatabase schema $Schema..."
    $previousPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $SourcePassword
        & $pgDump "-h" $SourceHost "-p" "$SourcePort" "-U" $SourceUser "-d" $SourceDatabase "--schema-only" "--schema=$Schema" "--no-owner" "--no-privileges" "--file=$dumpFile"
        if ($LASTEXITCODE -ne 0) {
            throw "pg_dump failed when exporting schema from ${SourceHost}:$SourcePort/$SourceDatabase"
        }

        $env:PGPASSWORD = $TargetPassword
        & $psql "-h" $TargetHost "-p" "$TargetPort" "-U" $TargetUser "-d" $TargetDatabase "-v" "ON_ERROR_STOP=1" "-f" $dumpFile
        if ($LASTEXITCODE -ne 0) {
            throw "psql failed when importing schema into ${TargetHost}:$TargetPort/$TargetDatabase"
        }
    } finally {
        $env:PGPASSWORD = $previousPassword
    }

    Write-Host "Schema imported into ${TargetHost}:$TargetPort/$TargetDatabase."
}

function Invoke-SqlFileIfExists(
    [string]$FilePath,
    [string]$TargetHost,
    [int]$TargetPort,
    [string]$TargetDatabase,
    [string]$TargetUser,
    [string]$TargetPassword
) {
    if (-not (Test-Path $FilePath)) {
        return
    }

    $existingFeatureTable = Invoke-PsqlScalar `
        -HostName $TargetHost `
        -Port $TargetPort `
        -Database $TargetDatabase `
        -User $TargetUser `
        -Password $TargetPassword `
        -Sql "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'DK3213242017'"
    if ($existingFeatureTable -ne "0") {
        Write-Host "PostGIS schema initialization skipped; public.DK3213242017 already exists."
        return
    }

    Write-Host "Running SQL initialization file: $FilePath"
    $previousPassword = $env:PGPASSWORD
    $env:PGPASSWORD = $TargetPassword
    try {
        & $psql "-h" $TargetHost "-p" "$TargetPort" "-U" $TargetUser "-d" $TargetDatabase "-v" "ON_ERROR_STOP=1" "-f" $FilePath
        if ($LASTEXITCODE -ne 0) {
            throw "SQL initialization failed: $FilePath"
        }
    } finally {
        $env:PGPASSWORD = $previousPassword
    }
}

function Write-RuntimeEnv(
    [string]$Path,
    [string]$DatabaseHost,
    [int]$DatabasePort,
    [string]$DatabaseName,
    [string]$DatabaseUser,
    [string]$DatabasePassword,
    [string]$GeoServerUrl,
    [string]$BackendUrl,
    [string]$FrontendUrl
) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    @(
        "DATABASE_HOST=$DatabaseHost",
        "DATABASE_PORT=$DatabasePort",
        "DATABASE_NAME=$DatabaseName",
        "DATABASE_USER=$DatabaseUser",
        "DATABASE_PASSWORD=$DatabasePassword",
        "GEOSERVER_PORT=8080",
        "GEOSERVER_URL=$GeoServerUrl",
        "BACKEND_HOST=0.0.0.0",
        "BACKEND_PORT=8000",
        "BACKEND_URL=$BackendUrl",
        "FRONTEND_HOST=127.0.0.1",
        "FRONTEND_PORT=5173",
        "FRONTEND_URL=$FrontendUrl"
    ) | Set-Content -Path $Path -Encoding UTF8
}

if (-not (Test-Path $installMarker)) {
    throw "Install marker was not found. Run: powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1"
}

if ((Test-Path $initMarker) -and (-not $Force)) {
    Write-Host "Init marker already exists: $initMarker"
    Write-Host "Use -Force to re-run initialization and refresh the marker."
    exit 0
}

& (Join-Path $PSScriptRoot "start-postgres.ps1") `
    -Port $DbPort `
    -DbName $DbName `
    -DbUser $DbUser `
    -DbPassword $DbPassword `
    -NonInteractive

$effectiveDbPort = if ($env:DATABASE_PORT) { [int]$env:DATABASE_PORT } else { $DbPort }
$effectiveDbName = if ($env:DATABASE_NAME) { $env:DATABASE_NAME } else { $DbName }
$effectiveDbUser = if ($env:DATABASE_USER) { $env:DATABASE_USER } else { $DbUser }
$effectiveDbPassword = if ($env:DATABASE_PASSWORD) { $env:DATABASE_PASSWORD } else { $DbPassword }

if ($ImportSchemaFromSource) {
    Import-PublicSchemaFromExistingDatabase `
        -SourceHost $SchemaSourceHost `
        -SourcePort $SchemaSourcePort `
        -SourceDatabase $SchemaSourceDbName `
        -SourceUser $SchemaSourceUser `
        -SourcePassword $SchemaSourcePassword `
        -TargetHost "127.0.0.1" `
        -TargetPort $effectiveDbPort `
        -TargetDatabase $effectiveDbName `
        -TargetUser $effectiveDbUser `
        -TargetPassword $effectiveDbPassword `
        -Schema $SchemaName
}

Invoke-SqlFileIfExists `
    -FilePath $sqlInitFile `
    -TargetHost "127.0.0.1" `
    -TargetPort $effectiveDbPort `
    -TargetDatabase $effectiveDbName `
    -TargetUser $effectiveDbUser `
    -TargetPassword $effectiveDbPassword

$pythonExe = Ensure-BackendPythonEnvironment

$previousDbHost = $env:DATABASE_HOST
$previousDbPort = $env:DATABASE_PORT
$previousDbName = $env:DATABASE_NAME
$previousDbUser = $env:DATABASE_USER
$previousDbPassword = $env:DATABASE_PASSWORD
try {
    $env:DATABASE_HOST = "127.0.0.1"
    $env:DATABASE_PORT = "$effectiveDbPort"
    $env:DATABASE_NAME = $effectiveDbName
    $env:DATABASE_USER = $effectiveDbUser
    $env:DATABASE_PASSWORD = $effectiveDbPassword

    Push-Location $backendPath
    try {
        & $pythonExe "-m" "app.db.bootstrap" "--schema"
        if ($LASTEXITCODE -ne 0) {
            throw "Backend database bootstrap failed."
        }
    } finally {
        Pop-Location
    }
} finally {
    $env:DATABASE_HOST = $previousDbHost
    $env:DATABASE_PORT = $previousDbPort
    $env:DATABASE_NAME = $previousDbName
    $env:DATABASE_USER = $previousDbUser
    $env:DATABASE_PASSWORD = $previousDbPassword
}

& (Join-Path $PSScriptRoot "start-geoserver.ps1") `
    -DbPort $effectiveDbPort `
    -DbName $effectiveDbName `
    -DbUser $effectiveDbUser `
    -DbPassword $effectiveDbPassword `
    -LayerSrs "EPSG:4527" `
    -NonInteractive

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
Write-RuntimeEnv `
    -Path $runtimeEnvFile `
    -DatabaseHost "127.0.0.1" `
    -DatabasePort $effectiveDbPort `
    -DatabaseName $effectiveDbName `
    -DatabaseUser $effectiveDbUser `
    -DatabasePassword $effectiveDbPassword `
    -GeoServerUrl "http://127.0.0.1:8080/geoserver" `
    -BackendUrl "http://127.0.0.1:8000" `
    -FrontendUrl "http://127.0.0.1:5173"

$marker = [ordered]@{
    platform = "windows"
    initializedAt = (Get-Date).ToString("o")
    database = $effectiveDbName
    databasePort = "$effectiveDbPort"
    geoserverUrl = "http://127.0.0.1:8080/geoserver"
}

($marker | ConvertTo-Json) | Set-Content -Path $initMarker -Encoding UTF8

Write-Host "Initialization passed."
Write-Host "Marker written: $initMarker"
Write-Host "Runtime config written: $runtimeEnvFile"
Write-Host "Next step: powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1"
