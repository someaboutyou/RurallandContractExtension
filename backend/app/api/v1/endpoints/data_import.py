from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.data_import import DataImportBatchCreate, DataImportBatchRead, DataImportRowRead
from app.schemas.pagination import PageResponse
from app.schemas.response import ApiResponse
from app.services.data_import_service import data_import_service

router = APIRouter()


@router.get("", response_model=ApiResponse[PageResponse[DataImportBatchRead]])
def list_import_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": data_import_service.list_batches(db, page=page, page_size=page_size, keyword=keyword, current_user=current_user)}


@router.post("", response_model=ApiResponse[DataImportBatchRead])
def create_import_batch(
    payload: DataImportBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": data_import_service.create_batch(db, payload.model_dump(), current_user)}


@router.get("/templates/{file_type}")
def download_import_template(
    file_type: str,
    current_user: User = Depends(require_permission("contractors.view")),
):
    filename, content = data_import_service.build_template_csv(file_type)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/templates/{file_type}/field-notes")
def download_import_template_field_notes(
    file_type: str,
    current_user: User = Depends(require_permission("contractors.view")),
):
    filename, content = data_import_service.build_template_notes_csv(file_type)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{batch_id}/files", response_model=ApiResponse[DataImportBatchRead])
async def upload_import_file(
    batch_id: int,
    file_type: str = Query(alias="fileType"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": await data_import_service.upload_csv(db, batch_id, file_type, file, current_user)}


@router.post("/{batch_id}/archive", response_model=ApiResponse[DataImportBatchRead])
async def upload_import_archive(
    batch_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": await data_import_service.upload_archive(db, batch_id, file, current_user)}


@router.post("/{batch_id}/gdb", response_model=ApiResponse[DataImportBatchRead])
async def upload_import_gdb(
    batch_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": await data_import_service.upload_gdb_archive(db, batch_id, file, current_user)}


@router.get("/{batch_id}/rows", response_model=ApiResponse[PageResponse[DataImportRowRead]])
def list_import_rows(
    batch_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": data_import_service.list_rows(db, batch_id, page, page_size, status_filter)}


@router.get("/{batch_id}/failed-rows.csv")
def download_failed_rows(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    filename, content = data_import_service.build_failed_rows_csv(db, batch_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
