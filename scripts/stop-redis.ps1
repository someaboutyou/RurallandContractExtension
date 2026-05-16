$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "runtime"
$stateDir = Join-Path $runtimeRoot ".state"
$redisHome = Join-Path $runtimeRoot "windows\redis"
$redisCli = Join-Path $redisHome "redis-cli.exe"
$redisServer = Join-Path $redisHome "redis-server.exe"
$redisData = Join-Path $runtimeRoot "data\redis"
$port = if ($env:REDIS_PORT) { [int]$env:REDIS_PORT } else { 16379 }
$hostName = "127.0.0.1"

function Stop-ProcessTreeById([int]$ProcessId, [string]$Reason) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }
    Write-Host "Stopping process tree $ProcessId ($Reason)..."
    & taskkill.exe /PID $ProcessId /T /F | Out-Host
}

if (Test-Path $redisCli) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $redisCli "-h" $hostName "-p" "$port" "shutdown" "save" *> $null
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

Start-Sleep -Seconds 1

$pidFile = Join-Path $stateDir "redis.pid"
if (Test-Path $pidFile) {
    $raw = (Get-Content -Raw -Path $pidFile).Trim()
    if ($raw -match '^\d+$') {
        Stop-ProcessTreeById ([int]$raw) "Redis pid file"
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

$redisPathPart = $redisHome.Replace("/", "\").ToLowerInvariant()
try {
    $items = @(Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -ieq "redis-server.exe") -and
        ([string]$_.CommandLine).Replace("/", "\").ToLowerInvariant().Contains($redisPathPart)
    })
    foreach ($item in $items) {
        Stop-ProcessTreeById ([int]$item.ProcessId) "Redis runtime"
    }
} catch {
    Write-Host "Redis process scan skipped: $($_.Exception.Message)"
}

$connections = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
foreach ($pid in @($connections | Select-Object -ExpandProperty OwningProcess -Unique)) {
    if ($pid -and $pid -gt 0) {
        Stop-ProcessTreeById ([int]$pid) "Redis port $port"
    }
}

Write-Host "Redis stopped. Persistent files remain under $redisData"
