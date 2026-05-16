param(
    [switch]$WithFrontend
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "runtime"
$stateDir = Join-Path $runtimeRoot ".state"
$installMarker = Join-Path $stateDir "installed.json"
$initMarker = Join-Path $stateDir "initialized.json"
$runtimeEnvFile = Join-Path $stateDir "runtime.env"
$backendScript = Join-Path $PSScriptRoot "start-backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "start-frontend.ps1"

$dbHost = "127.0.0.1"
$dbPort = "15432"
$dbName = "erlunyanbao"
$dbUser = "RurallandContractExtension"
$dbPassword = "RurallandContractExtension"

function Import-RuntimeEnv([string]$Path) {
    if (-not (Test-Path $Path)) {
        return
    }
    foreach ($line in Get-Content -Path $Path) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
            continue
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
        }
    }
}

if (-not (Test-Path $installMarker)) {
    Write-Host "System is not installed yet. Running install..."
    & (Join-Path $PSScriptRoot "install.ps1")
    if (-not (Test-Path $installMarker)) {
        throw "Install did not complete. Marker was not created: $installMarker"
    }
}

if (-not (Test-Path $initMarker)) {
    Write-Host "System is installed but not initialized yet. Running init..."
    & (Join-Path $PSScriptRoot "init.ps1") `
        -DbPort ([int]$dbPort) `
        -DbName $dbName `
        -DbUser $dbUser `
        -DbPassword $dbPassword
    if (-not (Test-Path $initMarker)) {
        throw "Initialization did not complete. Marker was not created: $initMarker"
    }
}

if (-not (Test-Path $runtimeEnvFile)) {
    Write-Host "Runtime config was not found. Refreshing initialization metadata..."
    & (Join-Path $PSScriptRoot "init.ps1") `
        -DbPort ([int]$dbPort) `
        -DbName $dbName `
        -DbUser $dbUser `
        -DbPassword $dbPassword `
        -Force
    if (-not (Test-Path $runtimeEnvFile)) {
        throw "Runtime config was not created: $runtimeEnvFile"
    }
}

Import-RuntimeEnv $runtimeEnvFile
$dbHost = if ($env:DATABASE_HOST) { $env:DATABASE_HOST } else { $dbHost }
$dbPort = if ($env:DATABASE_PORT) { $env:DATABASE_PORT } else { $dbPort }
$dbName = if ($env:DATABASE_NAME) { $env:DATABASE_NAME } else { $dbName }
$dbUser = if ($env:DATABASE_USER) { $env:DATABASE_USER } else { $dbUser }
$dbPassword = if ($env:DATABASE_PASSWORD) { $env:DATABASE_PASSWORD } else { $dbPassword }

$pgDataDir = Join-Path $runtimeRoot "data\pgdata"
if ($dbPassword -eq "RurallandContractExtension" -and (Test-Path (Join-Path $pgDataDir "PG_VERSION"))) {
    Write-Host "Database password is still the default value. Re-initializing with a random password..."
    & (Join-Path $PSScriptRoot "init.ps1") `
        -DbPort ([int]$dbPort) `
        -DbName $dbName `
        -DbUser $dbUser `
        -DbPassword $dbPassword `
        -Force
    if (-not (Test-Path $runtimeEnvFile)) {
        throw "Re-initialization failed. Runtime config was not created."
    }
    Import-RuntimeEnv $runtimeEnvFile
    $dbHost = if ($env:DATABASE_HOST) { $env:DATABASE_HOST } else { $dbHost }
    $dbPort = if ($env:DATABASE_PORT) { $env:DATABASE_PORT } else { $dbPort }
    $dbName = if ($env:DATABASE_NAME) { $env:DATABASE_NAME } else { $dbName }
    $dbUser = if ($env:DATABASE_USER) { $env:DATABASE_USER } else { $dbUser }
    $dbPassword = if ($env:DATABASE_PASSWORD) { $env:DATABASE_PASSWORD } else { $dbPassword }
}

& (Join-Path $PSScriptRoot "start-postgres.ps1") -Port ([int]$dbPort) -DbName $dbName -DbUser $dbUser -DbPassword $dbPassword
$redisPort = if ($env:REDIS_PORT) { [int]$env:REDIS_PORT } else { 16379 }
& (Join-Path $PSScriptRoot "start-redis.ps1") -Port $redisPort

$dbHost = if ($env:DATABASE_HOST) { $env:DATABASE_HOST } else { $dbHost }
$dbPort = if ($env:DATABASE_PORT) { $env:DATABASE_PORT } else { $dbPort }
$dbName = if ($env:DATABASE_NAME) { $env:DATABASE_NAME } else { $dbName }
$dbUser = if ($env:DATABASE_USER) { $env:DATABASE_USER } else { $dbUser }
$dbPassword = if ($env:DATABASE_PASSWORD) { $env:DATABASE_PASSWORD } else { $dbPassword }

& (Join-Path $PSScriptRoot "start-geoserver.ps1") `
    -DbHost $dbHost `
    -DbPort ([int]$dbPort) `
    -DbName $dbName `
    -DbUser $dbUser `
    -DbPassword $dbPassword

$dbHost = if ($env:DATABASE_HOST) { $env:DATABASE_HOST } else { $dbHost }
$dbPort = if ($env:DATABASE_PORT) { $env:DATABASE_PORT } else { $dbPort }
$dbName = if ($env:DATABASE_NAME) { $env:DATABASE_NAME } else { $dbName }
$dbUser = if ($env:DATABASE_USER) { $env:DATABASE_USER } else { $dbUser }
$dbPassword = if ($env:DATABASE_PASSWORD) { $env:DATABASE_PASSWORD } else { $dbPassword }

$backendProcess = Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$backendScript`"" -WorkingDirectory $projectRoot -PassThru
Set-Content -Path (Join-Path $stateDir "backend.pid") -Value $backendProcess.Id -Encoding ASCII

if ($WithFrontend) {
    $frontendProcess = Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$frontendScript`"" -WorkingDirectory $projectRoot -PassThru
    Set-Content -Path (Join-Path $stateDir "frontend.pid") -Value $frontendProcess.Id -Encoding ASCII
}

Write-Host ""
Write-Host "PostGIS:   127.0.0.1:$dbPort/$dbName"
Write-Host "Redis:     127.0.0.1:$redisPort"
Write-Host "GeoServer: http://127.0.0.1:8080/geoserver"
Write-Host "Backend:   http://127.0.0.1:8000"
if ($WithFrontend) {
    Write-Host "Frontend:  http://127.0.0.1:5173"
}
