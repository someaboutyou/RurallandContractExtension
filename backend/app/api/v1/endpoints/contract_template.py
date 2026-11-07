from fastapi import APIRouter, Depends, Response
from urllib.parse import quote

from app.api.deps import require_permission
from app.models.user import User
from app.schemas.contract_template import (
    ContractTemplatePreviewRead,
    ContractTemplatePreviewRequest,
    ContractTemplateRead,
    ContractTemplateUpdate,
    PrintTemplateListItem,
)
from app.schemas.response import ApiResponse
from app.services.contract_template_admin_service import contract_template_admin_service

router = APIRouter()

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@router.get("", response_model=ApiResponse[list[PrintTemplateListItem]])
def list_print_templates(
    _: User = Depends(require_permission("contract_templates.manage")),
):
    """打印模板母版清单（模板管理页左侧面板）。"""
    return {"data": contract_template_admin_service.list_print_templates()}


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


@router.get("/{template_key}/blank-word")
def download_blank_print_template(
    template_key: str,
    _: User = Depends(require_permission("contract_templates.manage")),
):
    """下载「无内容数据」的 Word：模板以空白上下文渲染后转写为 .docx。"""
    payload = contract_template_admin_service.render_blank_word(template_key)
    meta = contract_template_admin_service.template_registry[template_key]
    filename = meta.get("blank_filename") or f"{meta['name'].removesuffix('模板')}.docx"
    return Response(
        content=payload,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )
