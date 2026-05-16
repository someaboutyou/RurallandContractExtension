param(
    [switch]$SkipFrontend,
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendPath = Join-Path $projectRoot "frontend"
$backendPath = Join-Path $projectRoot "backend"
$setupScript = Join-Path $backendPath "setup_cython.py"
$stateDir = Join-Path $projectRoot "runtime\.state"
$buildMarker = Join-Path $stateDir "built.json"

# ── Frontend ────────────────────────────────────────────────────────
if (-not $SkipFrontend) {
    Write-Host "=== Building frontend ==="
    if (-not (Test-Path (Join-Path $frontendPath "package.json"))) {
        throw "frontend/package.json not found."
    }
    Push-Location $frontendPath
    try {
        $npm = Get-Command npm -ErrorAction SilentlyContinue
        if (-not $npm) {
            throw "npm not found. Install Node.js to build the frontend."
        }
        Write-Host "  npm install..."
        $installOutput = & cmd /c "npm install 2>&1"
        if ($LASTEXITCODE -ne 0) {
            Write-Host $installOutput
            throw "npm install failed."
        }

        Write-Host "  npm run build..."
        $buildOutput = & cmd /c "npm run build 2>&1"
        if ($LASTEXITCODE -ne 0) {
            Write-Host $buildOutput
            throw "npm run build failed."
        }
    } finally {
        Pop-Location
    }

    if (-not (Test-Path (Join-Path $frontendPath "dist\index.html"))) {
        throw "Frontend build output not found: frontend\dist\index.html"
    }
    Write-Host "  Frontend build complete: frontend/dist/"
    Write-Host ""
}

# ── Backend ─────────────────────────────────────────────────────────
if (-not $SkipBackend) {
    Write-Host "=== Building backend (Cython) ==="

    # Find a Python with Cython available
    $pythonExe = $null
    $possiblePythons = @(
        (Join-Path $projectRoot "runtime\windows\python\python.exe"),
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    )

    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    foreach ($candidate in $possiblePythons) {
        if (-not $candidate -or -not (Test-Path $candidate)) { continue }
        $null = & $candidate -c "import Cython" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $pythonExe = $candidate
            break
        }
    }
    $ErrorActionPreference = $prevEAP

    if (-not $pythonExe) {
        Write-Host "  Cython not found in any Python. Installing into runtime Python..."
        $runtimePython = Join-Path $projectRoot "runtime\windows\python\python.exe"
        if (-not (Test-Path $runtimePython)) {
            throw "Runtime Python not found at runtime\windows\python\python.exe. Cannot install Cython."
        }
        $pipOutput = & cmd /c "$runtimePython -m pip install cython --break-system-packages 2>&1"
        if ($LASTEXITCODE -ne 0) {
            Write-Host $pipOutput
            throw "Failed to install Cython."
        }
        $pythonExe = $runtimePython
    }

    Write-Host "  Python: $pythonExe"

    # Check that a C compiler is available for Cython
    Write-Host "  Checking C compiler..."
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $ccTest = & cmd /c "$pythonExe -c `"from setuptools._distutils.ccompiler import new_compiler; c = new_compiler(); print(type(c).__name__)`" 2>&1"
    $ccOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEAP
    if (-not $ccOk) {
        Write-Host "  No C compiler detected."
        Write-Host ""
        Write-Host "  Cython requires Microsoft C++ Build Tools to compile .py → .pyd."
        Write-Host "  Install with:"
        Write-Host "    winget install Microsoft.VisualStudio.2022.BuildTools --override `"--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended`""
        Write-Host "  Or download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        Write-Host ""
        Write-Host "  To skip backend compilation and build frontend only:"
        Write-Host "    .\scripts\build.cmd -SkipBackend"
        throw "C compiler not available. Install MSVC Build Tools or use -SkipBackend."
    }
    Write-Host "  Compiler: OK"

    Write-Host "  Compiling backend/app/**/*.py -> backend\dist\.pyd"

    Push-Location $backendPath
    try {
        # Clean previous build artifacts and dist
        $buildDir = Join-Path $backendPath "build"
        $distDir = Join-Path $backendPath "dist"
        if (Test-Path $buildDir) {
            Remove-Item -Recurse -Force -LiteralPath $buildDir
        }
        if (Test-Path $distDir) {
            Remove-Item -Recurse -Force -LiteralPath $distDir
        }

        $cythonOutput = & cmd /c "$pythonExe $setupScript build_ext --build-lib dist 2>&1"
        if ($LASTEXITCODE -ne 0) {
            Write-Host $cythonOutput
            Write-Host ""
            Write-Host "  To skip backend compilation and build frontend only:"
            Write-Host "    .\scripts\build.cmd -SkipBackend"
            throw "Cython compilation failed. Install MSVC Build Tools or use -SkipBackend."
        }

        # Remove the cython build cache
        if (Test-Path $buildDir) {
            Remove-Item -Recurse -Force -LiteralPath $buildDir
        }

        # Remove __pycache__ directories from dist
        Get-ChildItem -Path $distDir -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    } finally {
        Pop-Location
    }

    # Verify compilation from dist/
    Write-Host "  Verifying compilation..."
    Push-Location (Join-Path $backendPath "dist")
    try {
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $verifyOutput = & $pythonExe -c "from app.main import app; print('  Import OK')" 2>&1
        $ErrorActionPreference = $prevEAP
        if ($LASTEXITCODE -ne 0) {
            Write-Host $verifyOutput
            throw "Post-build import check failed. The compiled backend cannot be imported."
        }
    } finally {
        Pop-Location
    }

    Write-Host "  Backend build complete."
    Write-Host ""
}

# ── Marker ──────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$buildInfo = @{
    builtAt = (Get-Date -Format "o")
    platform = "windows"
} | ConvertTo-Json
Set-Content -Path $buildMarker -Value $buildInfo -Encoding UTF8

Write-Host "=== Build complete ==="
Write-Host "  Frontend: frontend/dist/"
Write-Host "  Backend:  backend/dist/ (compiled .pyd)"
Write-Host ""
Write-Host "Next: .\scripts\package.cmd"
