$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = if ($env:BACKEND_DIST -eq "1") {
    Join-Path $projectRoot "backend\dist"
} else {
    Join-Path $projectRoot "backend"
}
$portablePython = Join-Path $projectRoot "runtime\windows\python\python.exe"
$runtimeEnvFile = Join-Path $projectRoot "runtime\.state\runtime.env"
$runtimeLogDir = Join-Path $projectRoot "runtime\logs"
$backendLogFile = Join-Path $runtimeLogDir "backend.log"
$pythonExe = $portablePython

function Disable-DevCompiledModules([string]$BackendPath, [string]$ProjectRoot) {
    if ($env:BACKEND_DIST -eq "1") {
        return
    }
    $appPath = Join-Path $BackendPath "app"
    if (-not (Test-Path $appPath)) {
        return
    }
    $backupRoot = Join-Path $ProjectRoot "runtime\.state\dev-pyd-backup"
    Get-ChildItem -Path $appPath -Recurse -File -Filter "*.pyd" -ErrorAction SilentlyContinue | ForEach-Object {
        $sourceName = $_.Name -replace "\.cp\d+.*\.pyd$", ".py"
        $sourcePy = Join-Path $_.DirectoryName $sourceName
        if (-not (Test-Path $sourcePy)) {
            return
        }
        $relativePath = $_.FullName.Substring($BackendPath.Length + 1)
        $targetPath = Join-Path $backupRoot $relativePath
        $targetDir = Split-Path -Parent $targetPath
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        Move-Item -LiteralPath $_.FullName -Destination $targetPath -Force
        Write-Host "Moved compiled module for dev source: $relativePath"
    }
}

if (Test-Path $runtimeEnvFile) {
    foreach ($line in Get-Content -Path $runtimeEnvFile) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
            continue
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
        }
    }
}

if ([string]::IsNullOrWhiteSpace($pythonExe) -or -not (Test-Path $pythonExe)) {
    throw "Python not found. Put portable Python under runtime\windows\python."
}

& $pythonExe "-c" "import fastapi, uvicorn, sqlalchemy, psycopg, pydantic_settings, fiona, redis" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Backend Python dependencies are missing in runtime\windows\python. Install backend\requirements.txt into the bundled runtime Python before deployment."
}

New-Item -ItemType Directory -Force -Path $runtimeLogDir | Out-Null
Disable-DevCompiledModules -BackendPath $backendPath -ProjectRoot $projectRoot

Push-Location $backendPath
try {
    $backendHost = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "0.0.0.0" }
    $backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
    "[$(Get-Date -Format o)] Starting backend on ${backendHost}:${backendPort}" | Out-File -FilePath $backendLogFile -Append -Encoding utf8
    & cmd /c "`"$pythonExe`" -u -m uvicorn app.main:app --host $backendHost --port $backendPort >> `"$backendLogFile`" 2>&1"
}
finally {
    Pop-Location
}
