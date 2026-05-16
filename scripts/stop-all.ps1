$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "runtime"
$stateDir = Join-Path $runtimeRoot ".state"
$runtimeWindows = Join-Path $runtimeRoot "windows"

function Stop-ProcessTreeById([int]$ProcessId, [string]$Reason) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }

    Write-Host "Stopping process tree $ProcessId ($Reason)..."
    & taskkill.exe /PID $ProcessId /T /F | Out-Host
}

function Stop-PidFile([string]$Name) {
    $pidFile = Join-Path $stateDir "$Name.pid"
    if (-not (Test-Path $pidFile)) {
        return
    }

    $raw = (Get-Content -Raw -Path $pidFile).Trim()
    if ($raw -match '^\d+$') {
        Stop-ProcessTreeById ([int]$raw) "$Name pid file"
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

function Get-ProcessCommandLine([int]$ProcessId) {
    $item = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($item) {
        return [string]$item.CommandLine
    }
    return ""
}

function Stop-MatchingProcesses([scriptblock]$Predicate, [string]$Reason) {
    $items = @(Get-CimInstance Win32_Process | Where-Object { & $Predicate $_ })
    foreach ($item in $items) {
        Stop-ProcessTreeById ([int]$item.ProcessId) $Reason
    }
}

function Stop-ProcessesOnPort([int]$Port, [string]$Reason) {
    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    $pids = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($pid in $pids) {
        if ($pid -and $pid -gt 0) {
            Stop-ProcessTreeById ([int]$pid) "$Reason port $Port"
        }
    }
}

function Test-ProcessMatchesRuntimePath($Process, [string]$PathPart) {
    $commandLine = [string]$Process.CommandLine
    return $commandLine -and $commandLine.Replace("/", "\").ToLowerInvariant().Contains($PathPart.ToLowerInvariant())
}

Write-Host "Stopping backend and frontend windows..."
Stop-PidFile "backend"
Stop-PidFile "frontend"

Write-Host "Stopping GeoServer..."
try {
    & (Join-Path $PSScriptRoot "stop-geoserver.ps1")
} catch {
    Write-Host "GeoServer graceful stop failed: $($_.Exception.Message)"
}

Start-Sleep -Seconds 3

$geoPathPart = (Join-Path $runtimeWindows "geoserver").Replace("/", "\")
$jdkPathPart = (Join-Path $runtimeWindows "jdk").Replace("/", "\")
Stop-MatchingProcesses {
    param($p)
    ($p.Name -ieq "java.exe") -and (
        (Test-ProcessMatchesRuntimePath $p $geoPathPart) -or
        ((Test-ProcessMatchesRuntimePath $p $jdkPathPart) -and ([string]$p.CommandLine).ToLowerInvariant().Contains("geoserver"))
    )
} "GeoServer runtime java"
Stop-MatchingProcesses {
    param($p)
    ($p.Name -ieq "cmd.exe") -and (Test-ProcessMatchesRuntimePath $p $geoPathPart)
} "GeoServer startup shell"
Stop-ProcessesOnPort 8080 "GeoServer"

Write-Host "Stopping backend/frontend residual processes..."
$backendPathPart = (Join-Path $projectRoot "backend").Replace("/", "\")
$frontendPathPart = (Join-Path $projectRoot "frontend").Replace("/", "\")
$pythonPathPart = (Join-Path $runtimeWindows "python").Replace("/", "\")
Stop-MatchingProcesses {
    param($p)
    ($p.Name -imatch "python|python.exe") -and
    (Test-ProcessMatchesRuntimePath $p $pythonPathPart) -and
    ([string]$p.CommandLine).ToLowerInvariant().Contains("uvicorn")
} "Backend runtime python"
Stop-MatchingProcesses {
    param($p)
    ($p.Name -imatch "node|node.exe|npm|npm.cmd") -and
    (Test-ProcessMatchesRuntimePath $p $frontendPathPart)
} "Frontend node"
Stop-ProcessesOnPort 8000 "Backend"
Stop-ProcessesOnPort 5173 "Frontend"

Write-Host "Stopping Redis..."
try {
    & (Join-Path $PSScriptRoot "stop-redis.ps1")
} catch {
    Write-Host "Redis graceful stop failed: $($_.Exception.Message)"
}

Start-Sleep -Seconds 2

Write-Host "Stopping PostgreSQL..."
try {
    & (Join-Path $PSScriptRoot "stop-postgres.ps1")
} catch {
    Write-Host "PostgreSQL graceful stop failed: $($_.Exception.Message)"
}

Start-Sleep -Seconds 3

$postgresPathPart = (Join-Path $runtimeWindows "postgresql").Replace("/", "\")
$redisPathPart = (Join-Path $runtimeWindows "redis").Replace("/", "\")
Stop-MatchingProcesses {
    param($p)
    ($p.Name -ieq "redis-server.exe") -and (Test-ProcessMatchesRuntimePath $p $redisPathPart)
} "Redis runtime"
Stop-ProcessesOnPort 16379 "Redis"
Stop-MatchingProcesses {
    param($p)
    ($p.Name -ieq "postgres.exe") -and (Test-ProcessMatchesRuntimePath $p $postgresPathPart)
} "PostgreSQL runtime"
Stop-ProcessesOnPort 15432 "PostgreSQL"

$remaining = @()
$remaining += @(Get-CimInstance Win32_Process | Where-Object {
    (Test-ProcessMatchesRuntimePath $_ $postgresPathPart) -or
    (Test-ProcessMatchesRuntimePath $_ $redisPathPart) -or
    (Test-ProcessMatchesRuntimePath $_ $geoPathPart) -or
    (Test-ProcessMatchesRuntimePath $_ $pythonPathPart -and ([string]$_.CommandLine).ToLowerInvariant().Contains("uvicorn"))
})
$remainingPorts = @(Get-NetTCPConnection -LocalPort 8000, 8080, 15432, 16379, 5173 -State Listen -ErrorAction SilentlyContinue)

if ($remaining.Count -gt 0 -or $remainingPorts.Count -gt 0) {
    Write-Host "Some related processes or ports are still active:"
    $remaining | Select-Object Name, ProcessId, CommandLine | Format-List
    $remainingPorts | Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table
    throw "stop-all completed with residual processes."
}

Write-Host "All related runtime processes are stopped."
