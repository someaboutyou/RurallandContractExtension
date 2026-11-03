# -*- coding: utf-8 -*-
"""
移动端 Web 资源热更：检查 + 下载。

设计要点（详见 docs 与 scripts/publish_web_update.py）：
- 发布物：`backend/storage/app-updates/latest.json`（清单）+ `bundle-<版本>.zip`（dist 打包）。
  与 license 同目录模式：文件即状态，发布脚本写文件即发布，无需接口/管理页。
- **免登录**：更新检查发生在登录之前（也可能发生在 license 失效时），
  路由不带鉴权依赖，且 `LicenseCheckMiddleware._API_WHITELIST` 必须放行本前缀。
- 口径：客户端带着自己的 `bundle_version` 来问；**仅当清单版本比客户端新**才下发
  （版本号 yyyyMMddHHmm 字符串比较即时间序）。只判"不一致"会造成降级——
  先打进 APK、后发布的中间版本会被服务器旧清单覆盖（2026-09-30 事故：OCR 按钮被吃掉）。
  「是否可装」由客户端再核一道 `min_native_version_code`（新 Web 依赖新原生插件时由发布者抬高）。
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from app.schemas.response import ApiResponse

router = APIRouter()

# ⛔ 存储路径一律走 app.paths（编译布局下裸 parents[N] 会解析到 backend/dist/storage）
from app.paths import STORAGE_DIR

UPDATES_DIR = STORAGE_DIR / "app-updates"
MANIFEST_FILE = UPDATES_DIR / "latest.json"


def _load_manifest() -> dict | None:
    """读取当前发布的清单；文件缺失/损坏返回 None（表现为「无更新」，绝不抛 500 卡住 App）。"""
    try:
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict) or not manifest.get("version"):
        return None
    return manifest


@router.get("/check")
def check_update(
    response: Response,
    platform: str = "android",
    native_version_code: int = 0,
    bundle_version: str = "",
) -> ApiResponse:
    """客户端冷启动/回前台时调用：比对版本决定要不要下载。

    - `bundle_version` 与清单一致 → `action: "none"`（已是最新）。
    - 不一致 → `action: "web"`，返回清单字段；`native_version_code` 仅用于日志观测，
      客户端自行用 `min_native_version_code` 决定装不装。
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    manifest = _load_manifest()
    if manifest is None or str(manifest.get("version", "")) <= bundle_version:
        # 清单缺失 / 客户端已是同版本或更新版本 → 无需更新（防降级）
        return ApiResponse(data={"action": "none", "bundle": None})

    return ApiResponse(
        data={
            "action": "web",
            "bundle": {
                "version": manifest.get("version"),
                "sha256": manifest.get("sha256"),
                "size": manifest.get("size"),
                "file": manifest.get("file"),
                "min_native_version_code": manifest.get("min_native_version_code", 0),
                "notes": manifest.get("notes", ""),
                "published_at": manifest.get("published_at"),
            },
        }
    )


@router.get("/download")
def download_bundle(response: Response) -> FileResponse:
    """下载当前发布的 Web 包 zip。文件名取自清单并做目录穿越校验。"""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    manifest = _load_manifest()
    if manifest is None:
        raise HTTPException(status_code=404, detail="no update published")

    file_name = str(manifest.get("file") or "")
    target = (UPDATES_DIR / file_name).resolve()
    if (
        not file_name
        or target.parent != UPDATES_DIR
        or target.suffix.lower() != ".zip"
        or not target.is_file()
    ):
        raise HTTPException(status_code=404, detail="bundle file missing")

    return FileResponse(
        target,
        media_type="application/zip",
        filename=file_name,
        headers={"X-Bundle-Version": str(manifest.get("version", ""))},
    )
