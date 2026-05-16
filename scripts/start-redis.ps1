param(
    [int]$Port = 16379,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "runtime"
$redisHome = Join-Path $runtimeRoot "windows\redis"
$redisData = Join-Path $runtimeRoot "data\redis"
$logDir = Join-Path $runtimeRoot "logs"
$stateDir = Join-Path $runtimeRoot ".state"
$redisServer = Join-Path $redisHome "redis-server.exe"
$redisCli = Join-Path $redisHome "redis-cli.exe"
$redisLog = Join-Path $logDir "redis.log"
$redisHost = "127.0.0.1"

function Require-File([string]$Path, [string]$Message) {
    if (-not (Test-Path $Path)) {
        throw $Message
    }
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

function Test-PortInUse([int]$PortToCheck) {
    $connection = Get-NetTCPConnection -LocalPort $PortToCheck -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    return $null -ne $connection
}

function Test-RedisReady([int]$PortToCheck) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $redisCli "-h" $redisHost "-p" "$PortToCheck" "ping" 2>$null
        return ($LASTEXITCODE -eq 0) -and ((($output | Out-String).Trim()) -eq "PONG")
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

Require-File $redisServer "Redis server not found: $redisServer. Put portable Redis under runtime\windows\redis."
Require-File $redisCli "Redis CLI not found: $redisCli"

New-Item -ItemType Directory -Force -Path $redisData, $logDir, $stateDir | Out-Null

if (Test-RedisReady $Port) {
    Write-Host "Redis is already running on ${redisHost}:$Port."
} else {
    if (Test-PortInUse $Port) {
        throw "Port $Port is already in use and does not respond as Redis."
    }

    Write-Host "Starting Redis on ${redisHost}:$Port..."
    $args = @(
        "--bind", $redisHost,
        "--port", "$Port",
        "--dir", $redisData,
        "--dbfilename", "dump.rdb",
        "--appendonly", "yes",
        "--appendfilename", "appendonly.aof",
        "--logfile", $redisLog
    )
    $process = Start-Process -FilePath $redisServer -ArgumentList $args -WorkingDirectory $redisHome -WindowStyle Hidden -PassThru
    Set-Content -Path (Join-Path $stateDir "redis.pid") -Value $process.Id -Encoding ASCII

    for ($i = 0; $i -lt 20; $i++) {
        if (Test-RedisReady $Port) { break }
        Start-Sleep -Milliseconds 500
    }

    if (-not (Test-RedisReady $Port)) {
        throw "Redis startup timed out. Check $redisLog"
    }
}

$env:REDIS_HOST = $redisHost
$env:REDIS_PORT = "$Port"
$env:REDIS_DB = "0"
$env:REDIS_KEY_PREFIX = "rlce"

Write-Host "Redis ready: ${redisHost}:$Port"
Write-Host "Redis data: $redisData"
