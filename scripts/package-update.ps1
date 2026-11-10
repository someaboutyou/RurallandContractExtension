# -*- Command: 前后端增量更新包 -*-
<#
.SYNOPSIS
    只打 backend\dist（Cython .pyd）+ frontend\dist 的增量更新包，用于已部署机器的日常升级。

.DESCRIPTION
    与整包（package.ps1，~466MB）相对的轻量通道：
    - 包内容：backend\dist + frontend\dist + 更新说明.txt，约 34MB / ~390 文件；
    - 不含 runtime（PG/GeoServer/JDK/Python）、不含 backend\.env / storage / runtime\data，
      所以覆盖解压**不可能**碰到现场数据、授权与密钥；
    - 数据库结构升级不需要手工操作：目标机重启后端时 lifespan 的 bootstrap
      （create_all + upgrade_schema + sequences + seed 缺则补）自动完成；
    - 若 scripts\ 下的启动脚本也有改动，请改发整包（本包不带 scripts）。

.PARAMETER Version
    版本号，默认 0.1.0。

.PARAMETER OutputDir
    zip 输出目录，默认 dist\。

.PARAMETER SkipBuild
    跳过 build（frontend\dist 与 backend\dist 已是最新时用）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\package-update.cmd
    powershell -ExecutionPolicy Bypass -File .\scripts\package-update.ps1 -SkipBuild
#>
param(
    [string]$Version = "0.1.0",
    [string]$OutputDir,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$projectName = (Split-Path -Leaf $projectRoot)
# ⛔ 文件名带时分（同整包口径）：同日多包同名曾在目标机拷错包（2026-10-18 事故）
$dateSuffix = (Get-Date).ToString("yyyyMMdd-HHmm")
$outputName = "update-${projectName}-v${Version}-${dateSuffix}"

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
    Write-Host "Skipping build (-SkipBuild). Using existing dist artifacts."
}

$backendDist = Join-Path $projectRoot "backend\dist"
$frontendDist = Join-Path $projectRoot "frontend\dist"
if (-not (Test-Path (Join-Path $backendDist "app"))) {
    throw "backend\dist\app not found. Run build first (or drop -SkipBuild)."
}
if (-not (Test-Path (Join-Path $frontendDist "index.html"))) {
    throw "frontend\dist\index.html not found. Run build first (or drop -SkipBuild)."
}

# ── Collect to temp ────────────────────────────────────────────────
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "pkg-update-${projectName}"
if (Test-Path $tempDir) {
    Remove-Item -Recurse -Force -LiteralPath $tempDir
}
New-Item -ItemType Directory -Force -Path (Join-Path $tempDir "backend\dist") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $tempDir "frontend\dist") | Out-Null

robocopy $backendDist (Join-Path $tempDir "backend\dist") /E /NFL /NDL /NJH /NJS /NODCOPY
if ($LASTEXITCODE -ge 8) { throw "robocopy backend\dist failed: $LASTEXITCODE" }
robocopy $frontendDist (Join-Path $tempDir "frontend\dist") /E /NFL /NDL /NJH /NJS /NODCOPY
if ($LASTEXITCODE -ge 8) { throw "robocopy frontend\dist failed: $LASTEXITCODE" }

# ⛔ 这里**不能**删 .py：backend\dist 里有 15 个 setup_cython 有意保留的合法
# 运行时模块（app\main.py、app\db\bootstrap.py、data_import 包等，无对应 .pyd），
# 删了它们后端直接 ImportError（2026-11-10 实测踩过：首版脚本删了 .py 导致包残缺）。
# 与整包口径一致：backend\dist 原样进包。只清 __pycache__。
Get-ChildItem -Path $tempDir -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ── 更新说明 ────────────────────────────────────────────────────────
$readme = @"
${projectName} 增量更新包 v${Version}（${dateSuffix}）

包内容：backend\dist（编译后端）+ frontend\dist（前端构建产物），不含 runtime / 数据 / 授权。

目标机更新步骤（已安装机器）：
  1. 停后端服务（8000 端口进程）。前端由后端直接 serve，无需单独停；
     PG / GeoServer / Redis 不受本包影响，可以不停。
  2. 解压本 zip，将 backend\dist 整体覆盖到安装目录的 backend\dist，
     frontend\dist 整体覆盖到 frontend\dist。
     ⛔ 覆盖前建议备份原 backend\dist（改名 dist.prev-时间戳 即可）。
  3. 启动后端（scripts\start-backend.cmd 或 start-all.cmd）。
     数据库结构变更会在启动时自动迁移，无需手工执行 SQL。
  4. 浏览器 Ctrl+F5 强刷一次（前端文件名带 hash，普通刷新可能用旧缓存）。

注意：
  - 本包不带 scripts\。若启动脚本也有改动，请改发整包（scripts\package.cmd）。
  - 手机端如需同步前端，请在打包机上执行：
    runtime\windows\python\python.exe scripts\publish_web_update.py --notes "增量更新 v${Version}"
"@
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $tempDir "更新说明.txt"), $readme, $utf8NoBom)

# ── Package ────────────────────────────────────────────────────────
$zipPath = Join-Path $OutputDir "${outputName}.zip"
Write-Host "Creating archive: $zipPath"
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath -Force
Remove-Item -Recurse -Force -LiteralPath $tempDir

Write-Host ""
Write-Host "Update package created: $zipPath"
Write-Host "Size: $([math]::Round((Get-Item $zipPath).Length / 1MB, 1)) MB"
Write-Host ""
Write-Host "Target machine steps: see 更新说明.txt inside the zip."
