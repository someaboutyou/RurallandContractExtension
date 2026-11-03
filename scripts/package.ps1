param(
    [string]$OutputDir,
    [string]$Version = "0.1.0",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$projectName = (Split-Path -Leaf $projectRoot)
# ⛔ 文件名必须带时分：同一天多次打包会产生同名 zip（2026-10-18 踩过——上午的
# 旧 pyd 包和下午的修复包同名，目标机拷错包导致"修复无效"的假象）
$dateSuffix = (Get-Date).ToString("yyyyMMdd-HHmm")
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
    # 运行临时目录：曾混入 5 个 1.2G 测试 TIFF + raster-publish 产物（占包体积 76%+）
    "runtime\temp",
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
    # 运行业务数据与授权文件：安装包应是干净部署件，数据不随包走
    "backend\storage",
    # ⛔ robocopy /XD 不接受通配路径，dist.prev-* 等模式放安全网清理（见下）
    # 安卓工程与 APK 构建产物：部署机不需要（APK 走 app-updates 通道分发）
    "android",
    # 工具/会话目录
    ".claude",
    ".workbuddy",
    ".tmp-visual",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "docs",
    "datas"
)

# 通配排除项：robocopy 阶段不排除（复制进 temp 后由下方安全网按模式删除）
$excludedDirPatterns = @(
    "backend\dist.prev-*",
    "backend\build.prev-*"
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
foreach ($relativePath in ($excludedDirs + $excludedDirPatterns)) {
    # 这两个目录被主 robocopy 排除后由上方流程"显式重新拷入" temp，
    # 安全网不得再删（历史 bug：backend/dist 拷进包里又被这里删掉，部署件始终缺编译后端）
    if ($relativePath -in @("frontend", "backend\dist")) {
        continue
    }
    $path = Join-Path $tempDir $relativePath
    # 含通配符的排除项（如 backend\dist.prev-*）走 -Path 展开；字面路径走 -LiteralPath
    if ($relativePath.Contains("*")) {
        Get-Item -Path $path -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    } elseif (Test-Path -LiteralPath $path) {
        Remove-Item -Recurse -Force -LiteralPath $path -ErrorAction SilentlyContinue
    }
}

# Remove __pycache__ dirs from temp.
Get-ChildItem -Path $tempDir -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ── GeoServer 样式：datas 整体不随包走，但 geoserver-styles 是部署必需件 ──
# ⛔ 必须放在上面的安全网删除之后：安全网会把 temp\datas 整目录删掉
#（历史同款 bug：backend/dist 曾被拷入 temp 又被安全网删除，部署件缺编译后端）。
# 缺 SLD 的后果：图层照常发布但前端请求报 StyleNotDefined，地块整层看不见
#（2026-10-21 新机器安装踩过）。
$stylesSource = Join-Path $projectRoot "datas\geoserver-styles"
$stylesTarget = Join-Path $tempDir "datas\geoserver-styles"
if (Test-Path (Join-Path $stylesSource "survey_dk_result.sld")) {
    New-Item -ItemType Directory -Force -Path $stylesTarget | Out-Null
    robocopy $stylesSource $stylesTarget /E /NFL /NDL /NJH /NJS /NODCOPY
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed when copying datas/geoserver-styles with exit code $LASTEXITCODE"
    }
    Write-Host "GeoServer styles copied: datas\geoserver-styles ($(@(Get-ChildItem $stylesSource -Filter *.sld).Count) sld files)"
} else {
    throw "datas/geoserver-styles/survey_dk_result.sld not found. Packaging would ship GeoServer layers without styles (StyleNotDefined at request time). Restore the styles directory before packaging."
}

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
Write-Host "  Silent background start (no console windows): double-click .\scripts\start-production-silent.pyw"
Write-Host "Runtime data note: Redis persistence is stored under runtime\data\redis and is excluded from packages."

if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "NOTE: Compiled backend output is in backend\dist\."
    Write-Host "Source .py files under backend\app\ are preserved for continued development."
}
