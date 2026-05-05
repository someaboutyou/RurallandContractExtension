$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$portablePython = Join-Path $projectRoot "runtime\windows\python\python.exe"
$runtimeEnvFile = Join-Path $projectRoot "runtime\.state\runtime.env"
$pythonExe = $portablePython

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

& $pythonExe "-c" "import fastapi, uvicorn, sqlalchemy, psycopg, pydantic_settings, fiona" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Backend Python dependencies are missing in runtime\windows\python. Install backend\requirements.txt into the bundled runtime Python before deployment."
}

Push-Location $backendPath
try {
    $backendHost = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "0.0.0.0" }
    $backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
    & $pythonExe -m uvicorn app.main:app --host $backendHost --port $backendPort
}
finally {
    Pop-Location
}
