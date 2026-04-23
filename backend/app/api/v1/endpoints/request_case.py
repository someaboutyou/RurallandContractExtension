from pathlib import Path

from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.pagination import PageResponse
from app.schemas.request_case import (
    RequestCaseAttachmentRead,
    RequestCaseAuditAction,
    RequestCaseCreate,
    RequestCaseRead,
    RequestCaseUpdate,
    RequestCaseWorkflowViewRead,
)
from app.schemas.response import ApiResponse
from app.services.request_case_service import request_case_service

router = APIRouter()


@router.get("", response_model=ApiResponse[PageResponse[RequestCaseRead]])
def list_request_cases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.view")),
):
    return {
        "data": request_case_service.list_cases(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            status_filter=status_filter,
            current_user=current_user,
        )
    }


@router.get("/{case_id}", response_model=ApiResponse[RequestCaseRead])
def get_request_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.view")),
):
    return {"data": request_case_service.get_case(db, case_id, current_user)}


@router.get("/{case_id}/workflow-view", response_model=ApiResponse[RequestCaseWorkflowViewRead])
def get_request_case_workflow_view(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.view")),
):
    return {"data": request_case_service.get_case_workflow_view(db, case_id, current_user)}


@router.post("/{case_id}/attachments", response_model=ApiResponse[RequestCaseAttachmentRead], status_code=status.HTTP_201_CREATED)
def upload_request_case_attachment(
    case_id: int,
    file: UploadFile = File(...),
    category: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.view")),
):
    return {
        "data": request_case_service.upload_attachment(
            db,
            case_id,
            upload_file=file,
            category=category,
            current_user=current_user,
        )
    }


@router.get("/{case_id}/attachments/{attachment_id}/download")
def download_request_case_attachment(
    case_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.view")),
):
    attachment = request_case_service.get_attachment(db, case_id, attachment_id, current_user)
    return FileResponse(
        path=Path(attachment.storage_path),
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_name,
    )


@router.get("/{case_id}/attachments/download-all")
def download_request_case_attachments_bundle(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.view")),
):
    filename, content = request_case_service.build_attachment_archive(db, case_id, current_user)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(BytesIO(content), media_type="application/zip", headers=headers)


@router.delete("/{case_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request_case_attachment(
    case_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.view")),
):
    request_case_service.delete_attachment(db, case_id, attachment_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("", response_model=ApiResponse[RequestCaseRead], status_code=status.HTTP_201_CREATED)
def create_request_case(
    payload: RequestCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.manage")),
):
    return {"data": request_case_service.create_case(db, payload.model_dump(), current_user)}


@router.put("/{case_id}", response_model=ApiResponse[RequestCaseRead])
def update_request_case(
    case_id: int,
    payload: RequestCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.manage")),
):
    return {"data": request_case_service.update_case(db, case_id, payload.model_dump(), current_user)}


@router.post("/{case_id}/submit", response_model=ApiResponse[RequestCaseRead])
def submit_request_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.submit")),
):
    return {"data": request_case_service.submit_case(db, case_id, current_user)}


@router.post("/{case_id}/approve", response_model=ApiResponse[RequestCaseRead])
def approve_request_case(
    case_id: int,
    payload: RequestCaseAuditAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.view")),
):
    return {"data": request_case_service.approve_case(db, case_id, current_user, payload.comment)}


@router.post("/{case_id}/reject", response_model=ApiResponse[RequestCaseRead])
def reject_request_case(
    case_id: int,
    payload: RequestCaseAuditAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.view")),
):
    return {"data": request_case_service.reject_case(db, case_id, current_user, payload.comment)}


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.manage")),
):
    request_case_service.delete_case(db, case_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
