from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.request_attachment_template import (
    RequestAttachmentTemplateCreate,
    RequestAttachmentTemplateRead,
    RequestAttachmentTemplateUpdate,
)
from app.schemas.response import ApiResponse
from app.services.request_attachment_template_service import request_attachment_template_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[RequestAttachmentTemplateRead]])
def list_request_attachment_templates(
    tenant_code: str | None = Query(default=None, alias="tenantCode"),
    request_type: str | None = Query(default=None, alias="requestType"),
    stage_code: str | None = Query(default=None, alias="stageCode"),
    source: str | None = Query(default=None),
    parent_id: int | None = Query(default=None, alias="parentId"),
    apply_parent_filter: bool = Query(default=False, alias="applyParentFilter"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("requests.manage")),
):
    return {
        "data": request_attachment_template_service.list_templates(
            db,
            tenant_code,
            request_type=request_type,
            stage_code=stage_code,
            source=source,
            parent_id=parent_id,
            apply_parent_filter=apply_parent_filter,
        )
    }


@router.post("", response_model=ApiResponse[RequestAttachmentTemplateRead], status_code=status.HTTP_201_CREATED)
def create_request_attachment_template(
    payload: RequestAttachmentTemplateCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("requests.manage")),
):
    try:
        return {"data": request_attachment_template_service.create_template(db, payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/{template_id}", response_model=ApiResponse[RequestAttachmentTemplateRead])
def update_request_attachment_template(
    template_id: int,
    payload: RequestAttachmentTemplateUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("requests.manage")),
):
    try:
        return {"data": request_attachment_template_service.update_template(db, template_id, payload.model_dump())}
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) == "template not found" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request_attachment_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("requests.manage")),
):
    try:
        request_attachment_template_service.delete_template(db, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
