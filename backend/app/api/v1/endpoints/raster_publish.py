"""
影像发布 API 端点
"""

import os
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import get_current_user, require_permission
from app.models.user import User
from app.schemas.response import ApiResponse
from app.services.raster_publish_service import raster_publish_service

router = APIRouter()


class ValidateTifRequest(BaseModel):
    tif_path: str


class PublishRequest(BaseModel):
    tif_path: str
    clip_geojson: dict | None = None
    store_name: str | None = None


@router.post("/validate-tif", response_model=ApiResponse[dict])
def validate_tif(
    payload: ValidateTifRequest,
    _: User = Depends(require_permission("layers.manage")),
):
    """验证tif文件是否存在并返回元数据"""
    try:
        info = raster_publish_service.validate_tif(payload.tif_path)
        return {"data": info}
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/upload-shp", response_model=ApiResponse[dict])
async def upload_shp(
    file: UploadFile = File(...),
    _: User = Depends(require_permission("layers.manage")),
):
    """上传shp压缩包，返回GeoJSON范围"""
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请上传.zip格式的Shapefile压缩包"
        )

    # 保存上传文件
    temp_dir = raster_publish_service.temp_dir
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"upload_{uuid.uuid4().hex[:8]}.zip")

    try:
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)

        result = raster_publish_service.parse_shp_zip(temp_path)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    finally:
        try:
            os.remove(temp_path)
        except:
            pass


@router.post("/publish", response_model=ApiResponse[dict])
def publish_raster(
    payload: PublishRequest,
    _: User = Depends(require_permission("layers.manage")),
):
    """启动影像发布任务（异步）"""
    # 验证tif存在
    try:
        raster_publish_service.validate_tif(payload.tif_path)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    # 创建任务
    task_id = raster_publish_service.create_task()

    # 后台线程执行发布
    def _run():
        try:
            result = raster_publish_service.publish_raster(
                task_id=task_id,
                tif_path=payload.tif_path,
                clip_geojson=payload.clip_geojson,
                store_name=payload.store_name,
            )
            raster_publish_service.set_task_result(task_id, result)
        except Exception as e:
            raster_publish_service._update_progress(task_id, -1, f"发布失败: {str(e)}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"data": {"task_id": task_id}}


@router.get("/progress/{task_id}", response_model=ApiResponse[dict])
def get_progress(
    task_id: str,
    _: User = Depends(require_permission("layers.manage")),
):
    """查询发布任务进度"""
    task = raster_publish_service.get_task_progress(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return {"data": task}
