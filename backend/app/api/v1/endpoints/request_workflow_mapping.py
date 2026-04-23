from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.request_workflow_mapping import (
    RequestWorkflowMappingCreate,
    RequestWorkflowMappingRead,
    RequestWorkflowMappingUpdate,
    RequestWorkflowOptionsPayload,
)
from app.schemas.response import ApiResponse
from app.services.request_workflow_mapping_service import request_workflow_mapping_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[RequestWorkflowMappingRead]])
def list_request_workflow_mappings(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": request_workflow_mapping_service.list_mappings(db)}


@router.get("/options", response_model=ApiResponse[RequestWorkflowOptionsPayload])
def list_request_workflow_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.manage")),
):
    return {"data": request_workflow_mapping_service.list_workflow_options(db, current_user)}


@router.post("", response_model=ApiResponse[RequestWorkflowMappingRead], status_code=status.HTTP_201_CREATED)
def create_request_workflow_mapping(
    payload: RequestWorkflowMappingCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": request_workflow_mapping_service.create_mapping(db, payload.model_dump())}


@router.put("/{mapping_id}", response_model=ApiResponse[RequestWorkflowMappingRead])
def update_request_workflow_mapping(
    mapping_id: int,
    payload: RequestWorkflowMappingUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": request_workflow_mapping_service.update_mapping(db, mapping_id, payload.model_dump())}


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request_workflow_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    request_workflow_mapping_service.delete_mapping(db, mapping_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
