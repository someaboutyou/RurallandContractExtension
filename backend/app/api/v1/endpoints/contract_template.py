from fastapi import APIRouter, Depends

from app.api.deps import require_permission
from app.models.user import User
from app.schemas.contract_template import (
    ContractTemplatePreviewRead,
    ContractTemplatePreviewRequest,
    ContractTemplateRead,
    ContractTemplateUpdate,
)
from app.schemas.response import ApiResponse
from app.services.contract_template_admin_service import contract_template_admin_service

router = APIRouter()


@router.get("/contract", response_model=ApiResponse[ContractTemplateRead])
def get_contract_template(
    _: User = Depends(require_permission("contract_templates.manage")),
):
    return {"data": contract_template_admin_service.get_contract_template()}


@router.get("/{template_key}", response_model=ApiResponse[ContractTemplateRead])
def get_print_template(
    template_key: str,
    _: User = Depends(require_permission("contract_templates.manage")),
):
    return {"data": contract_template_admin_service.get_print_template(template_key)}


@router.put("/contract", response_model=ApiResponse[ContractTemplateRead])
def update_contract_template(
    payload: ContractTemplateUpdate,
    _: User = Depends(require_permission("contract_templates.manage")),
):
    return {"data": contract_template_admin_service.update_contract_template(payload.content)}


@router.put("/{template_key}", response_model=ApiResponse[ContractTemplateRead])
def update_print_template(
    template_key: str,
    payload: ContractTemplateUpdate,
    _: User = Depends(require_permission("contract_templates.manage")),
):
    return {"data": contract_template_admin_service.update_print_template(template_key, payload.content)}


@router.post("/contract/preview", response_model=ApiResponse[ContractTemplatePreviewRead])
def preview_contract_template(
    payload: ContractTemplatePreviewRequest,
    _: User = Depends(require_permission("contract_templates.manage")),
):
    return {"data": contract_template_admin_service.preview_contract_template(payload.content)}


@router.post("/{template_key}/preview", response_model=ApiResponse[ContractTemplatePreviewRead])
def preview_print_template(
    template_key: str,
    payload: ContractTemplatePreviewRequest,
    _: User = Depends(require_permission("contract_templates.manage")),
):
    return {"data": contract_template_admin_service.preview_print_template(template_key, payload.content)}
