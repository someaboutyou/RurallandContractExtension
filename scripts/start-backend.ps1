$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$pythonExe = "D:\Programs\anaconda3\envs\erlunyanbao\python.exe"

Push-Location $backendPath
try {
    & $pythonExe -m uvicorn app.main:app --reload
}
finally {
    Pop-Location
}
