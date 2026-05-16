param(
    [string]$OutputDir,
    [string]$Version = "0.1.0",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$projectName = (Split-Path -Leaf $projectRoot)
$dateSuffix = (Get-Date).ToString("yyyyMMdd")
$outputName = "${projectName}-v${Version}-${dateSuffix}"

if (-not $OutputDir) {
    $OutputDir = Join-Path $projectRoot "dist"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# ── Build ───────────────────────────────────────────────────────────
if (-not $SkipBuild) {
    Write-Host "=== Running build (frontend + backend) ==="
    & (Join-Path $PSScriptRoot "build.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed."
    }
    Write-Host ""
} else {
    Write-Host "Skipping build (-SkipBuild). Using existing build artifacts."
    $frontendDist = Join-Path $projectRoot "frontend\dist\index.html"
    if (-not (Test-Path $frontendDist)) {
        Write-Host "WARNING: frontend/dist/ not found. Package will not include frontend UI."
    }
}

# ── Copy to temp ────────────────────────────────────────────────────
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "pkg-${projectName}"
if (Test-Path $tempDir) {
    Remove-Item -Recurse -Force -LiteralPath $tempDir
}

$excludedDirs = @(
    "runtime\data",
    "runtime\logs",
    "runtime\.state",
    "runtime\windows\postgresql\pgAdmin 4",
    "runtime\windows\geoserver\data_dir\gwc",
    "runtime\windows\geoserver\data_dir\gwc-layers",
    "runtime\windows\geoserver\data_dir\logs",
    "runtime\windows\geoserver\data_dir\workspaces",
    "runtime\windows\jdk\jmods",
    "frontend",
    "backend\app",
    "backend\__pycache__",
    "backend\.venv",
    "backend\.env",
    "backend\build",
    "backend\dist",
    "docs",
    "datas",
    ".claude",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "dist"
)

$excludedFiles = @(
    "*.pyc",
    "*.c",
    "*.pdb",
    "src.zip",
    "*.md",
    "*.docx",
    "*.pdf",
    ".DS_Store",
    "Thumbs.db"
)

Write-Host "Copying project to temporary packaging directory..."
Write-Host "  Source: $projectRoot"
Write-Host "  Temp:   $tempDir"

$excludedDirPaths = $excludedDirs | ForEach-Object { Join-Path $projectRoot $_ }
$xdArgs = @("/XD") + $excludedDirPaths
$xfArgs = @("/XF") + $excludedFiles

robocopy $projectRoot $tempDir /E /NFL /NDL /NJH /NJS /NODCOPY @xdArgs @xfArgs
if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed with exit code $LASTEXITCODE"
}

# Copy only the compiled frontend output needed at runtime.
$frontendDistSource = Join-Path $projectRoot "frontend\dist"
$frontendDistTarget = Join-Path $tempDir "frontend\dist"
if (Test-Path (Join-Path $frontendDistSource "index.html")) {
    New-Item -ItemType Directory -Force -Path $frontendDistTarget | Out-Null
    robocopy $frontendDistSource $frontendDistTarget /E /NFL /NDL /NJH /NJS /NODCOPY
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed when copying frontend/dist with exit code $LASTEXITCODE"
    }
} else {
    Write-Host "WARNING: frontend/dist/index.html not found. Package will not include frontend UI."
}

# Copy compiled backend dist/ into temp
$backendDistSource = Join-Path $projectRoot "backend\dist"
$backendDistTarget = Join-Path $tempDir "backend\dist"
if (Test-Path $backendDistSource) {
    New-Item -ItemType Directory -Force -Path $backendDistTarget | Out-Null
    robocopy $backendDistSource $backendDistTarget /E /NFL /NDL /NJH /NJS /NODCOPY
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed when copying backend/dist with exit code $LASTEXITCODE"
    }
} else {
    throw "backend/dist/ not found. Run build first."
}

# Remove excluded directories from temp as a safety net before compression.
foreach ($relativePath in $excludedDirs) {
    if ($relativePath -eq "frontend") {
        continue
    }
    $path = Join-Path $tempDir $relativePath
    if (Test-Path $path) {
        Remove-Item -Recurse -Force -LiteralPath $path -ErrorAction SilentlyContinue
    }
}

# Remove __pycache__ dirs from temp.
Get-ChildItem -Path $tempDir -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ── Package ─────────────────────────────────────────────────────────
$zipPath = Join-Path $OutputDir "${outputName}.zip"
Write-Host "Creating archive: $zipPath"
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath -Force

Remove-Item -Recurse -Force -LiteralPath $tempDir

Write-Host ""
Write-Host "Package created: $zipPath"
Write-Host "Size: $([math]::Round((Get-Item $zipPath).Length / 1MB, 1)) MB"
Write-Host ""
Write-Host "Deployment steps on target machine:"
Write-Host "  1. Extract ${outputName}.zip"
Write-Host "  2. Run: powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1"
Write-Host "  3. Run: powershell -ExecutionPolicy Bypass -File .\scripts\init.ps1"
Write-Host "  4. Run: .\scripts\start-all.cmd"
Write-Host "Runtime data note: Redis persistence is stored under runtime\data\redis and is excluded from packages."

if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "NOTE: Compiled backend output is in backend\dist\."
    Write-Host "Source .py files under backend\app\ are preserved for continued development."
}
