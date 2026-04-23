from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.workflow_definition import (
    WorkflowDefinitionActivate,
    WorkflowDefinitionListItem,
    WorkflowDefinitionPublish,
    WorkflowDefinitionRead,
    WorkflowDefinitionSave,
    WorkflowDefinitionValidate,
    WorkflowDefinitionValidationResult,
    WorkflowDefinitionVersionRead,
)
from app.services.workflow_definition_service import workflow_definition_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[WorkflowDefinitionListItem]])
def list_workflow_definitions(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": workflow_definition_service.list_definitions(db)}


@router.get("/{workflow_key}", response_model=ApiResponse[WorkflowDefinitionRead])
def get_workflow_definition(
    workflow_key: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": workflow_definition_service.get_definition(db, workflow_key)}


@router.post("/validate", response_model=ApiResponse[WorkflowDefinitionValidationResult])
def validate_workflow_definition(
    payload: WorkflowDefinitionValidate,
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": workflow_definition_service.validate_definition(payload.content)}


@router.put("/{workflow_key}", response_model=ApiResponse[WorkflowDefinitionRead], status_code=status.HTTP_200_OK)
def save_workflow_definition(
    workflow_key: str,
    payload: WorkflowDefinitionSave,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": workflow_definition_service.save_definition(db, workflow_key, payload.model_dump())}


@router.get("/{workflow_key}/versions", response_model=ApiResponse[list[WorkflowDefinitionVersionRead]])
def list_workflow_definition_versions(
    workflow_key: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": workflow_definition_service.list_versions(db, workflow_key)}


@router.post("/{workflow_key}/publish", response_model=ApiResponse[WorkflowDefinitionVersionRead])
def publish_workflow_definition(
    workflow_key: str,
    payload: WorkflowDefinitionPublish,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("roles.manage")),
):
    return {"data": workflow_definition_service.publish_definition(db, workflow_key, payload.model_dump(), current_user)}


@router.post("/{workflow_key}/activate", response_model=ApiResponse[WorkflowDefinitionVersionRead])
def activate_workflow_definition(
    workflow_key: str,
    payload: WorkflowDefinitionActivate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.manage")),
):
    return {"data": workflow_definition_service.activate_version(db, workflow_key, payload.versionId)}
