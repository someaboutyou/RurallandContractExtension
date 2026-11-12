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

    # ── 重打 UI 启动器 exe，保证包里的 RurallandLauncher.exe 与 launcher.py 同步 ──
    $launcherPy = Join-Path $projectRoot "UIexe\launcher.py"
    $launcherExe = Join-Path $projectRoot "UIexe\dist\RurallandLauncher.exe"
    if (Test-Path $launcherPy) {
        # ⛔ exe 被运行中的启动器进程占用时 PyInstaller 覆盖会报 WinError 5
        # （2026-11-10 实踩）。启动器只是控制壳，结束它不影响已启动的服务。
        Get-Process -Name "RurallandLauncher" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
        Write-Host "=== Building UI launcher (RurallandLauncher.exe) ==="
        & (Join-Path $projectRoot "UIexe\build.ps1")
        if ($LASTEXITCODE -ne 0) {
            throw "UI launcher build failed."
        }
        if (-not (Test-Path $launcherExe)) {
            throw "RurallandLauncher.exe not found after build."
        }
        Write-Host ""
    }
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
    # UIexe 打包目录：dist\RurallandLauncher.exe 是部署件要随包走；
    # build\ 是 PyInstaller 中间产物（~24MB），不需要
    "UIexe\build",
    # Python 运行时的编译期/包管理器元数据：运行时不需要（zoneinfo 在 share\ 里，⛔ 不能排）
    "runtime\windows\python\include",
    "runtime\windows\python\Tools",
    "runtime\windows\python\conda-meta",
    # conda Library 的编译期产物（头文件/.lib 链接库）；⛔ Library\bin 是运行时 DLL 不能排
    "runtime\windows\python\Library\include",
    "runtime\windows\python\Library\lib",
    # PostgreSQL 编译期/文档/安装器：运行时不需要
    # ⛔ postgresql\share 必须保留：extension\*.sql 全新安装 CREATE EXTENSION 要用，timezone 是时区库
    "runtime\windows\postgresql\include",
    "runtime\windows\postgresql\doc",
    "runtime\windows\postgresql\StackBuilder",
    # JDK 头文件与许可文本：运行时不需要
    "runtime\windows\jdk\include",
    "runtime\windows\jdk\legal",
    # 工具/会话目录
    ".claude",
    ".workbuddy",
    ".playwright-cli",
    ".tmp-visual",
    # 后端本地运行临时目录（根 runtime\temp 已排除，backend\runtime 是另一处）
    "backend\runtime",
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
    # 开发期散落在根目录的截图/日志/测试配置，部署包不需要
    "*.png",
    "*.log",
    "login.yaml",
    "login2.yaml",
    ".gitattributes",
    ".gitignore",
    "_check_import_rows.py",
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

# ── UI 启动器 exe 提到包根目录：用户解压后直接双击 ──
$launcherExeSource = Join-Path $projectRoot "UIexe\dist\RurallandLauncher.exe"
if (Test-Path $launcherExeSource) {
    Copy-Item -LiteralPath $launcherExeSource -Destination (Join-Path $tempDir "RurallandLauncher.exe") -Force
    Write-Host "Launcher copied to package root: RurallandLauncher.exe"
} else {
    Write-Host "WARNING: UIexe\dist\RurallandLauncher.exe not found. Package will not include the launcher UI."
}

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

# ── PostgreSQL bin 补 VC++ 运行库 DLL ────────────────────────────────
# postgres.exe -> icuuc67.dll -> MSVCP140.dll：部署机没装 VC++ 2015-2022
# 运行库时 postgres.exe 加载失败且无输出，initdb 报
# "no data was returned by command postgres.exe -V" / "program postgres is
# needed"（2026-11-11 部署机实踩）。initdb 不依赖 MSVCP140 能跑，症状掩盖真因。
# 从随包的 python 运行时把这组 DLL 拷进 postgresql\bin（exe 目录是 DLL
# 搜索第一顺位，整条依赖链都能解析，不依赖目标机 PATH/注册表）。
$vcDllNames = @(
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "vcruntime140_threads.dll"
)
$pgBinTarget = Join-Path $tempDir "runtime\windows\postgresql\bin"
$pythonRoot = Join-Path $tempDir "runtime\windows\python"
foreach ($dllName in $vcDllNames) {
    $src = Join-Path $pythonRoot $dllName
    $dst = Join-Path $pgBinTarget $dllName
    if ((Test-Path $dst) -or -not (Test-Path $src)) { continue }
    Copy-Item -LiteralPath $src -Destination $dst -Force
}
$missingVc = @($vcDllNames | Where-Object { -not (Test-Path (Join-Path $pgBinTarget $_)) })
if ($missingVc.Count -gt 0) {
    throw ("VC runtime DLLs missing from postgresql\bin after packaging: " + ($missingVc -join ", ") +
        ". Copy them from runtime\windows\python\ on the build machine before packaging.")
}
Write-Host "VC runtime DLLs ensured in postgresql\bin (msvcp140*/vcruntime140*)."

# ── Python 运行时去源码：.py → .pyc（sourceless），只对 temp 副本执行 ──
# ⛔ 绝不指向开发机的 runtime\windows\python（开发期需要源码）。
# 副本里 compileall + 把 __pycache__/*.pyc 移回原 .py 位置后删除 .py；
# CPython 官方 embeddable 发行版即此机制（python311.zip 内全是 .pyc）。
# 效果（2026-11-09 实测）：653M → 566M，减少约 87MB / 4600+ 个源码文件，
# 依赖导入 / 编译后端 app.main / 业务验收脚本三层冒烟全过。
$stripScript = Join-Path $PSScriptRoot "strip_python_sources.py"
$devPython = Join-Path $projectRoot "runtime\windows\python\python.exe"
if (-not (Test-Path $devPython)) {
    throw "runtime\windows\python\python.exe not found. Cannot run strip_python_sources."
}
& $devPython $stripScript (Join-Path $tempDir "runtime\windows\python")
if ($LASTEXITCODE -ne 0) {
    throw "strip_python_sources.py failed with exit code $LASTEXITCODE"
}
Write-Host "Python runtime stripped: .py sources converted to .pyc (sourceless)."

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
Write-Host "  4. Run: powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1"
Write-Host "  Graphical start/stop: double-click .\RurallandLauncher.exe (system control center)"
Write-Host "Runtime data note: Redis persistence is stored under runtime\data\redis and is excluded from packages."

if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "NOTE: Compiled backend output is in backend\dist\."
    Write-Host "Source .py files under backend\app\ are preserved for continued development."
}
