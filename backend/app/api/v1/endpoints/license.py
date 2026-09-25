# -*- coding: utf-8 -*-
"""
授权相关API
"""

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Response, UploadFile, File, HTTPException
from app.core.license import license_validator, LicenseStatus
from app.core.license.machine_fingerprint import get_machine_fingerprint
from app.schemas.response import ApiResponse

router = APIRouter()

LICENSE_DIR = Path(__file__).resolve().parents[4] / "storage"
LICENSE_FILE = LICENSE_DIR / "license.dat"

# 授权状态必须实时，禁止任何中间层缓存
NO_STORE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


@router.get("/machine-code")
def get_machine_code() -> ApiResponse:
    """获取机器码"""
    fingerprint = get_machine_fingerprint()
    return ApiResponse(
        data={
            "machine_code": fingerprint,
            "message": "请将此机器码发送给授权方获取授权文件",
        }
    )


@router.get("/status")
def get_license_status(response: Response) -> ApiResponse:
    """获取授权状态

    每次调用都会依据授权文件的当前状态判断：文件被替换、删除或改名后立即生效，
    不需要重启后端。
    """
    response.headers.update(NO_STORE)
    result = license_validator.validate()

    data = {
        "status": result.status.value,
        "is_valid": result.status == LicenseStatus.VALID,
        "error_message": result.error_message,
    }

    if result.license_info:
        info = result.license_info
        data.update(
            {
                "region_code": info.region_code,
                "region_name": info.region_name,
                "region_level": info.region_level,
                "issued_at": info.issued_at.isoformat(),
                "expires_at": info.expires_at.isoformat() if info.expires_at else None,
                "features": info.features,
            }
        )

    return ApiResponse(data=data)


@router.post("/reload")
def reload_license() -> ApiResponse:
    """
    热重载授权文件

    将新的 license.dat 放入 storage 目录后，调用此接口即可生效，无需重启后端。
    """
    result = license_validator.reload()

    data = {
        "status": result.status.value,
        "is_valid": result.status == LicenseStatus.VALID,
        "error_message": result.error_message,
    }

    if result.license_info:
        info = result.license_info
        data.update(
            {
                "region_code": info.region_code,
                "region_name": info.region_name,
                "region_level": info.region_level,
            }
        )

    return ApiResponse(data=data)


@router.post("/upload")
async def upload_license(file: UploadFile = File(...)) -> ApiResponse:
    """
    上传授权文件

    - 如果已存在旧的授权文件，将其备份为 license.dat.bak.时间戳
    - 将上传的文件保存为 license.dat
    - 自动热重载并返回验证结果
    """
    LICENSE_DIR.mkdir(parents=True, exist_ok=True)

    # 备份旧文件
    if LICENSE_FILE.exists():
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = LICENSE_DIR / f"license.dat.bak.{timestamp}"
        shutil.copy2(LICENSE_FILE, backup)

    # 保存新文件
    content = await file.read()
    LICENSE_FILE.write_bytes(content)

    # 热重载并返回结果
    result = license_validator.reload()

    data = {
        "status": result.status.value,
        "is_valid": result.status == LicenseStatus.VALID,
        "error_message": result.error_message,
    }

    if result.license_info:
        info = result.license_info
        data.update(
            {
                "region_code": info.region_code,
                "region_name": info.region_name,
                "region_level": info.region_level,
            }
        )

    return ApiResponse(data=data)
