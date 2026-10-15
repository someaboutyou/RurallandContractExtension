from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.data_export import DataExport
from app.models.user import User
from app.schemas.data_export import DataExportCreate, DataExportRead, serialize_export
from app.schemas.pagination import PageResponse
from app.schemas.response import ApiResponse
from app.services.data_access_service import data_access_service
from app.services.data_export_service import data_export_service

router = APIRouter()

# 与 data_imports 同组，使用 contractors.view 作为准入判据
_EXPORT_PERM = "contractors.view"

# backend/storage/ 根目录
_STORAGE_ROOT = Path(__file__).resolve().parents[4] / "storage"

ZIP_MEDIA_TYPE = "application/zip"


def _content_disposition(filename: str) -> str:
    """中文文件名按 RFC 5987 编码，避免浏览器拿到乱码。"""
    quoted = quote(filename)
    return f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"


@router.post("", response_model=ApiResponse[DataExportRead])
def create_data_export(
    payload: DataExportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(_EXPORT_PERM)),
):
    """对某个区域（县/镇/村/组）发起数据导出。

    同步生成承包方清册 + 家庭成员两份 CSV 并打成 ZIP，记录落库后返回。
    """
    try:
        record = data_export_service.create_export(db, payload.model_dump(), current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"data": record}


@router.get("", response_model=ApiResponse[PageResponse[DataExportRead]])
def list_data_exports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(_EXPORT_PERM)),
):
    return {
        "data": data_export_service.list_exports(
            db, page=page, page_size=page_size, keyword=keyword, current_user=current_user
        )
    }


@router.get("/{export_id}/download")
def download_data_export(
    export_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(_EXPORT_PERM)),
):
    export = db.get(DataExport, export_id)
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出记录不存在")
    # ⛔ 与 clear/delete 同口径的显式归属校验（审计 M1）：不再依赖 ORM 全局
    # 过滤器隐式兜底——导出 ZIP 含承包方清册 + 家庭成员（大量个人信息），
    # 必须显式拦：租户不符 403，区域超出授权范围 403。
    try:
        data_export_service._tenant_check(db, export_id, current_user)
        data_access_service.ensure_region_in_scope(
            current_user, export.region_code, detail="无权下载该区域的数据导出"
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if getattr(export, "is_historical", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该导出已清除，产物文件不再保留")
    if not export.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该导出无可用文件")
    abs_path = _STORAGE_ROOT / export.file_path
    if not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出文件已不存在，请重新导出")
    content = abs_path.read_bytes()
    return Response(
        content=content,
        media_type=ZIP_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(export.file_name or f"export_{export_id}.zip")},
    )


@router.post("/{export_id}/clear", response_model=ApiResponse[DataExportRead])
def clear_data_export(
    export_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(_EXPORT_PERM)),
):
    """清除导出：删除服务器上的产物文件与以 id 命名的目录，记录置为历史（保留台账）。"""
    try:
        record = data_export_service.clear_export(db, export_id, current_user)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出记录不存在") from None
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权清除该导出记录") from None
    return {"data": DataExportRead(**serialize_export(record))}


@router.delete("/{export_id}", response_model=ApiResponse[dict])
def delete_data_export(
    export_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(_EXPORT_PERM)),
):
    try:
        data_export_service.delete_export(db, export_id, current_user)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出记录不存在") from None
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除该导出记录") from None
    return {"data": {"deleted": True, "id": export_id}}
