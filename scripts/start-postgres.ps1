param(
    [int]$Port = 15432,
    [string]$DbName = "erlunyanbao",
    [string]$DbUser = "RurallandContractExtension",
    [string]$DbPassword = "RurallandContractExtension",
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "runtime"
$pgHome = Join-Path $runtimeRoot "windows\postgresql"
$pgBin = Join-Path $pgHome "bin"
$pgData = Join-Path $runtimeRoot "data\pgdata"
$logDir = Join-Path $runtimeRoot "logs"
$pgCtl = Join-Path $pgBin "pg_ctl.exe"
$postgresExe = Join-Path $pgBin "postgres.exe"
$initDb = Join-Path $pgBin "initdb.exe"
$psql = Join-Path $pgBin "psql.exe"
$createdb = Join-Path $pgBin "createdb.exe"
$pgIsReady = Join-Path $pgBin "pg_isready.exe"
$pgLog = Join-Path $logDir "postgres.log"
$pgDirectLog = Join-Path $logDir "postgres-direct.log"
$pgHost = "127.0.0.1"

function Require-File([string]$Path, [string]$Message) {
    if (-not (Test-Path $Path)) {
        throw $Message
    }
}

function Read-Choice([string]$Prompt, [string[]]$Allowed, [string]$Default) {
    if ($NonInteractive) {
        return $Default
    }

    while ($true) {
        $answer = Read-Host $Prompt
        if ([string]::IsNullOrWhiteSpace($answer)) {
            $answer = $Default
        }
        if ($Allowed -contains $answer) {
            return $answer
        }
        Write-Host "Please enter: $($Allowed -join '/')"
    }
}

function ConvertTo-SqlLiteral([string]$Value) {
    return $Value.Replace("'", "''")
}

function Test-DatabaseExists([string]$Name) {
    $literal = ConvertTo-SqlLiteral $Name
    $result = & $psql "-h" "127.0.0.1" "-p" "$Port" "-U" $DbUser "-d" "postgres" "-tAc" "SELECT 1 FROM pg_database WHERE datname = '$literal'"
    $result = (($result | Out-String).Trim())
    return $result -eq "1"
}

function Test-ExtensionExists([string]$Name) {
    $literal = ConvertTo-SqlLiteral $Name
    $result = & $psql "-h" "127.0.0.1" "-p" "$Port" "-U" $DbUser "-d" $DbName "-tAc" "SELECT 1 FROM pg_extension WHERE extname = '$literal'"
    $result = (($result | Out-String).Trim())
    return $result -eq "1"
}

function Test-PortInUse([int]$PortToCheck) {
    $connection = Get-NetTCPConnection -LocalPort $PortToCheck -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    return $null -ne $connection
}

function Test-PostgresReady([int]$PortToCheck) {
    $status = Invoke-NativeStatus { & $pgIsReady "-h" $pgHost "-p" "$PortToCheck" "-U" $DbUser }
    return $status -eq 0
}

function Invoke-NativeStatus([scriptblock]$Command) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command *> $null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Get-RunningPgPort {
    $optsPath = Join-Path $pgData "postmaster.opts"
    if (-not (Test-Path $optsPath)) {
        return $null
    }

    $opts = Get-Content -Raw -Encoding ASCII $optsPath
    $match = [regex]::Match($opts, "(?:^|\s)-p\s+(\d+)")
    if ($match.Success) {
        return [int]$match.Groups[1].Value
    }
    return $null
}

Require-File $pgCtl "PostgreSQL not found: $pgCtl. Put portable PostgreSQL/PostGIS under runtime\windows\postgresql."
Require-File $postgresExe "postgres.exe not found: $postgresExe"
Require-File $initDb "initdb not found: $initDb"
Require-File $psql "psql not found: $psql"
Require-File $createdb "createdb not found: $createdb"
Require-File $pgIsReady "pg_isready not found: $pgIsReady"

New-Item -ItemType Directory -Force -Path $pgData, $logDir | Out-Null

$pgStatus = Invoke-NativeStatus { & $pgCtl "status" "-D" $pgData }
if ($pgStatus -eq 0) {
    $runningPort = Get-RunningPgPort
    if ($runningPort -and $runningPort -ne $Port) {
        Write-Host "PostgreSQL portable runtime is running on port $runningPort. Restarting on requested port $Port..."
        & $pgCtl "restart" "-D" $pgData "-l" $pgLog "-o" "-p $Port -h $pgHost"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to restart PostgreSQL on port $Port. Check $pgLog"
        }
    } elseif ($runningPort) {
        $Port = $runningPort
    }
    Write-Host "PostgreSQL is already running."
} else {
    $isInitialized = Test-Path (Join-Path $pgData "PG_VERSION")
    if ($isInitialized -and (Test-PostgresReady $Port)) {
        Write-Host "PostgreSQL is already accepting connections on port $Port."
    } else {
    if ((Test-PortInUse $Port) -and (-not $isInitialized)) {
        Write-Host "Port $Port is already in use by another process."
        $choice = Read-Choice "Choose: 1=use existing PostgreSQL on port $Port, 2=start portable PostgreSQL on another port, 3=exit [1/2/3]" @("1", "2", "3") "2"
        if ($choice -eq "1") {
            $env:PGPASSWORD = $DbPassword
            if (-not (Test-DatabaseExists $DbName)) {
                Write-Host "Database $DbName was not found on existing PostgreSQL."
                $dbChoice = Read-Choice "Choose: 1=create default database $DbName on existing PostgreSQL, 2=use another existing database, 3=exit [1/2/3]" @("1", "2", "3") "2"
                if ($dbChoice -eq "1") {
                    & $createdb "-h" $pgHost "-p" "$Port" "-U" $DbUser $DbName
                    if ($LASTEXITCODE -ne 0) {
                        throw "Failed to create database on existing PostgreSQL: $DbName"
                    }
                } elseif ($dbChoice -eq "2") {
                    if ($NonInteractive) {
                        throw "Cannot input a database name in NonInteractive mode. Use -DbName."
                    }
                    $existingDb = Read-Host "Enter existing database name"
                    if ([string]::IsNullOrWhiteSpace($existingDb) -or -not (Test-DatabaseExists $existingDb)) {
                        throw "Specified database does not exist: $existingDb"
                    }
                    $DbName = $existingDb
                } else {
                    throw "Database selection canceled."
                }
            }
            $env:DATABASE_HOST = $pgHost
            $env:DATABASE_PORT = "$Port"
            $env:DATABASE_NAME = $DbName
            $env:DATABASE_USER = $DbUser
            $env:DATABASE_PASSWORD = $DbPassword
            Write-Host "Using existing PostgreSQL: ${pgHost}:$Port/$DbName"
            return
        } elseif ($choice -eq "2") {
            if ($NonInteractive) {
                $Port = 15432
            } else {
                $newPort = Read-Host "Enter PostgreSQL port for portable runtime [15432]"
                if ([string]::IsNullOrWhiteSpace($newPort)) {
                    $newPort = "15432"
                }
                $Port = [int]$newPort
            }
        } else {
            throw "PostgreSQL startup canceled."
        }
    }

    if (-not $isInitialized) {
        $choice = Read-Choice "PostgreSQL data directory is not initialized. Initialize runtime\data\pgdata? [Y/n]" @("Y", "y", "N", "n") "Y"
        if ($choice -in @("N", "n")) {
            throw "PostgreSQL initialization canceled."
        }

        $nonPlaceholderItems = @(Get-ChildItem -LiteralPath $pgData -Force | Where-Object { $_.Name -ne ".gitkeep" })
        if ($nonPlaceholderItems.Count -gt 0) {
            throw "PostgreSQL data directory is not empty and is not initialized: $pgData. Move or clean this directory before initializing."
        }
        Remove-Item -LiteralPath (Join-Path $pgData ".gitkeep") -Force -ErrorAction SilentlyContinue

        $pwFile = Join-Path $logDir ".pgpass-init"
        Set-Content -Path $pwFile -Value $DbPassword -Encoding ASCII
        try {
            & $initDb "-D" $pgData "-U" $DbUser "--encoding=UTF8" "--locale=C" "--auth-host=scram-sha-256" "--auth-local=trust" "--pwfile=$pwFile"
            if ($LASTEXITCODE -ne 0) {
                throw "initdb failed for data directory: $pgData"
            }
        } finally {
            Remove-Item -LiteralPath $pwFile -Force -ErrorAction SilentlyContinue
        }
    }

    if (Test-PortInUse $Port) {
        Write-Host "Port $Port is already in use by another process."
        $choice = Read-Choice "Choose: 1=use existing PostgreSQL on port $Port, 2=start portable PostgreSQL on another port, 3=exit [1/2/3]" @("1", "2", "3") "2"
        if ($choice -eq "1") {
            $env:PGPASSWORD = $DbPassword
            if (-not (Test-DatabaseExists $DbName)) {
                throw "Database $DbName was not found on existing PostgreSQL. Rerun with -DbName for an existing database, or free port $Port and use portable PostgreSQL."
            }
            $env:DATABASE_HOST = $pgHost
            $env:DATABASE_PORT = "$Port"
            $env:DATABASE_NAME = $DbName
            $env:DATABASE_USER = $DbUser
            $env:DATABASE_PASSWORD = $DbPassword
            Write-Host "Using existing PostgreSQL: ${pgHost}:$Port/$DbName"
            return
        } elseif ($choice -eq "2") {
            if ($NonInteractive) {
                $Port = 15432
            } else {
                $newPort = Read-Host "Enter PostgreSQL port for portable runtime [15432]"
                if ([string]::IsNullOrWhiteSpace($newPort)) {
                    $newPort = "15432"
                }
                $Port = [int]$newPort
            }
            if (Test-PortInUse $Port) {
                throw "Port $Port is also in use. Choose a free port."
            }
        } else {
            throw "PostgreSQL startup canceled."
        }
    }

    & $pgCtl "start" "-D" $pgData "-l" $pgLog "-o" "-p $Port -h $pgHost"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "pg_ctl start failed. Trying direct postgres.exe startup..."
        $pgOutLog = Join-Path $logDir "postgres-direct.out.log"
        $pgErrLog = Join-Path $logDir "postgres-direct.err.log"
        Start-Process -FilePath $postgresExe `
            -ArgumentList @("-D", $pgData, "-p", "$Port", "-h", $pgHost) `
            -WorkingDirectory $pgHome `
            -RedirectStandardOutput $pgOutLog `
            -RedirectStandardError $pgErrLog `
            -WindowStyle Hidden | Out-Null
        Start-Sleep -Seconds 2
        if (-not (Test-PostgresReady $Port)) {
            throw "Failed to start PostgreSQL with data directory: $pgData. Check $pgLog and $pgErrLog"
        }
    }
    }
}

$env:PGPASSWORD = $DbPassword
for ($i = 0; $i -lt 30; $i++) {
    $readyStatus = Invoke-NativeStatus { & $pgIsReady "-h" $pgHost "-p" "$Port" "-U" $DbUser }
    if ($readyStatus -eq 0) { break }
    Start-Sleep -Seconds 1
}

& $pgIsReady "-h" $pgHost "-p" "$Port" "-U" $DbUser
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL startup timed out. Check $pgLog"
}

if (-not (Test-DatabaseExists $DbName)) {
    Write-Host "Database not found: $DbName"
    $choice = Read-Choice "Choose: 1=create default database $DbName, 2=use existing database, 3=exit [1/2/3]" @("1", "2", "3") "1"
    if ($choice -eq "1") {
        & $createdb "-h" "127.0.0.1" "-p" "$Port" "-U" $DbUser $DbName
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create database: $DbName"
        }
    } elseif ($choice -eq "2") {
        if ($NonInteractive) {
            throw "Cannot input an existing database name in NonInteractive mode. Use -DbName to specify an existing database."
        }
        $existingDb = Read-Host "Enter existing database name"
        if ([string]::IsNullOrWhiteSpace($existingDb)) {
            throw "Database name cannot be empty."
        }
        if (-not (Test-DatabaseExists $existingDb)) {
            throw "Specified database does not exist: $existingDb"
        }
        $DbName = $existingDb
    } else {
        throw "Database selection canceled."
    }
}

if (-not (Test-ExtensionExists "postgis")) {
    Write-Host "Database $DbName does not have the PostGIS extension enabled."
    $choice = Read-Choice "Run CREATE EXTENSION postgis? [Y/n]" @("Y", "y", "N", "n") "Y"
    if ($choice -in @("Y", "y")) {
        & $psql "-h" "127.0.0.1" "-p" "$Port" "-U" $DbUser "-d" $DbName "-c" "CREATE EXTENSION IF NOT EXISTS postgis;"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to enable PostGIS. Ensure runtime\windows\postgresql includes PostGIS files matching this PostgreSQL version."
        }
    } else {
        throw "Database $DbName does not have PostGIS enabled."
    }
}

if (-not (Test-ExtensionExists "postgis_topology")) {
    $choice = Read-Choice "Run CREATE EXTENSION postgis_topology? [Y/n]" @("Y", "y", "N", "n") "Y"
    if ($choice -in @("Y", "y")) {
        & $psql "-h" "127.0.0.1" "-p" "$Port" "-U" $DbUser "-d" $DbName "-c" "CREATE EXTENSION IF NOT EXISTS postgis_topology;"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Failed to enable postgis_topology. Basic postgis is available; check PostGIS files if topology is required."
        }
    }
}

$env:DATABASE_HOST = "127.0.0.1"
$env:DATABASE_PORT = "$Port"
$env:DATABASE_NAME = $DbName
$env:DATABASE_USER = $DbUser
$env:DATABASE_PASSWORD = $DbPassword

Write-Host "PostgreSQL/PostGIS ready: 127.0.0.1:$Port/$DbName"
