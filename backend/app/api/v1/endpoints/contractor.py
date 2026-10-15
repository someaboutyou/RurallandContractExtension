from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.contractor import (
    CadastralExportProgressRead,
    CadastralExportRequest,
    ContractorCreate,
    ContractorRead,
    ContractorUpdate,
    SurveySheetExportRequest,
)
from app.schemas.pagination import PageResponse
from app.schemas.response import ApiResponse
from app.services.cadastral_docx_service import cadastral_docx_service
from app.services.cadastral_export_service import cadastral_export_service
from app.services.contract_template_service import contract_template_service
from app.services.contractor_service import contractor_service
from app.services.data_access_service import data_access_service
from app.services.survey_sheet_docx_service import survey_sheet_docx_service

router = APIRouter()

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _content_disposition(filename: str) -> str:
    """中文文件名要按 RFC 5987 编码，否则浏览器拿到的是乱码。"""
    quoted = quote(filename)
    return f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"


@router.get("", response_model=ApiResponse[PageResponse[ContractorRead]])
def list_contractors(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    type_code: str | None = Query(default=None, alias="typeCode"),
    name: str | None = Query(default=None),
    member_name: str | None = Query(default=None, alias="memberName"),
    id_no: str | None = Query(default=None, alias="idNo"),
    address: str | None = Query(default=None),
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": contractor_service.list_contractors(
            db,
            page=page,
            page_size=page_size,
            current_user=current_user,
            keyword=keyword,
            type_code=type_code,
            name=name,
            member_name=member_name,
            id_no=id_no,
            address=address,
            region_code=region_code,
        )
    }


# 注意：本路由必须排在 "/{contractor_code}" 之前，否则会被路径参数吞掉。
@router.get("/cadastral-survey")
def print_cadastral_surveys(
    keyword: str | None = Query(default=None),
    type_code: str | None = Query(default=None, alias="typeCode"),
    name: str | None = Query(default=None),
    member_name: str | None = Query(default=None, alias="memberName"),
    id_no: str | None = Query(default=None, alias="idNo"),
    address: str | None = Query(default=None),
    region_code: str | None = Query(default=None, alias="regionCode"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """批量打印地籍调查表：按筛选条件分页取承包方，返回这一页的整套表格 HTML。

    每户输出 封面 + 发包方调查表 + 承包方调查表 + 每地块一套
    （承包地块调查表 + 界址点坐标成果表）。

    一个村可达上千户，整村一次渲染既慢又撑爆浏览器，因此调用方按页取数、
    自行拼到一个打印窗口里；本接口只负责"这一页"并回报 ``total`` 供其判断。
    """
    page_data = contractor_service.list_contractors(
        db,
        page=page,
        page_size=page_size,
        current_user=current_user,
        keyword=keyword,
        type_code=type_code,
        name=name,
        member_name=member_name,
        id_no=id_no,
        address=address,
        region_code=region_code,
    )
    total = page_data["total"]
    cbfbms = [item["code"] for item in page_data["items"] if item.get("code")]
    rendered = (
        contract_template_service.render_cadastral_survey_batch(db, cbfbms=cbfbms)
        if cbfbms
        else ""
    )
    return {
        "data": {
            "page": page,
            "pageSize": page_size,
            "total": total,
            "contractorCount": len(cbfbms),
            "hasMore": page * page_size < total,
            "cbfbms": cbfbms,
            "renderedHtml": rendered,
        }
    }


@router.post("/cadastral-survey/export", response_model=ApiResponse[dict])
def create_cadastral_survey_export(
    payload: CadastralExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """批量导出《地籍调查表》Word（后台逐户生成，打包 zip）。

    立即返回 ``taskId``，前端轮询进度接口；完成后从下载接口取 zip。
    """
    filters = {
        "keyword": payload.keyword,
        "name": payload.name,
        "member_name": payload.memberName,
        "id_no": payload.idNo,
        "address": payload.address,
        "region_code": payload.regionCode,
    }
    task_id = cadastral_export_service.create_task(
        filters=filters,
        user_id=current_user.id,
        region_label=(payload.regionLabel or payload.regionCode or "区域"),
    )
    return {"data": {"taskId": task_id}}


@router.get(
    "/cadastral-survey/export/{task_id}",
    response_model=ApiResponse[CadastralExportProgressRead],
)
def get_cadastral_survey_export_progress(
    task_id: str,
    current_user: User = Depends(require_permission("contractors.view")),
):
    try:
        progress = cadastral_export_service.get_progress(task_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if progress is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出任务不存在")
    return {"data": progress}


@router.get("/cadastral-survey/export/{task_id}/download")
def download_cadastral_survey_export(
    task_id: str,
    current_user: User = Depends(require_permission("contractors.view")),
):
    try:
        archive = cadastral_export_service.get_archive(task_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if archive is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="导出任务不存在或尚未完成"
        )
    filename, payload = archive
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


# ── 摸底表（2026-10-09 礼泉试点）：单户 Word 下载 + 区域批量导出 ────────────
# 注意：以下路由必须排在 "/{contractor_code}" 之前，否则会被路径参数吞掉。


def _download_survey_sheet_docx(
    contractor_code: str, sheet: str, db: Session, current_user: User
) -> Response:
    data_access_service.ensure_code_in_scope(current_user, contractor_code)
    try:
        payload, filename = survey_sheet_docx_service.render_contractor(
            db, cbfbm=contractor_code, sheet=sheet
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Response(
        content=payload,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("/{contractor_code}/land-change-sheet.docx")
def download_land_change_sheet_docx(
    contractor_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """单户《承包方包地变化情况摸底表》Word 下载。"""
    return _download_survey_sheet_docx(contractor_code, "land-change", db, current_user)


@router.get("/{contractor_code}/member-change-sheet.docx")
def download_member_change_sheet_docx(
    contractor_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """单户《承包农户家庭成员变化情况摸底表》Word 下载。"""
    return _download_survey_sheet_docx(contractor_code, "member-change", db, current_user)


@router.post("/survey-sheet/export", response_model=ApiResponse[dict])
def create_survey_sheet_export(
    payload: SurveySheetExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """批量导出摸底表 Word（后台逐户生成，打包 zip；与地籍调查表同一套任务设施）。"""
    filters = {
        "keyword": payload.keyword,
        "name": payload.name,
        "member_name": payload.memberName,
        "id_no": payload.idNo,
        "address": payload.address,
        "region_code": payload.regionCode,
    }
    try:
        task_id = cadastral_export_service.create_task(
            filters=filters,
            user_id=current_user.id,
            region_label=(payload.regionLabel or payload.regionCode or "区域"),
            sheet=payload.sheetType,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"data": {"taskId": task_id}}


@router.get(
    "/survey-sheet/export/{task_id}",
    response_model=ApiResponse[CadastralExportProgressRead],
)
def get_survey_sheet_export_progress(
    task_id: str,
    current_user: User = Depends(require_permission("contractors.view")),
):
    try:
        progress = cadastral_export_service.get_progress(task_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if progress is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出任务不存在")
    return {"data": progress}


@router.get("/survey-sheet/export/{task_id}/download")
def download_survey_sheet_export(
    task_id: str,
    current_user: User = Depends(require_permission("contractors.view")),
):
    try:
        archive = cadastral_export_service.get_archive(task_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if archive is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="导出任务不存在或尚未完成"
        )
    filename, payload = archive
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("/{contractor_code}/cadastral-survey.docx")
def download_cadastral_survey_docx(
    contractor_code: str,
    batch_id: int | None = Query(default=None, alias="batchId"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """单户《地籍调查表》Word 下载，文件名 ``CBFBM+CBFMC+地籍调查表``。"""
    # ⛔ 显式归属校验（审计 L1）：与列表/详情接口同口径，不再只依赖 ORM
    # 全局过滤器隐式兜底（防止未来新增非 scoped 模型或误用 skip_tenant_scope）。
    data_access_service.ensure_code_in_scope(current_user, contractor_code)
    payload, filename = cadastral_docx_service.render_contractor(
        db, cbfbm=contractor_code, batch_id=batch_id
    )
    return Response(
        content=payload,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("/{contractor_code}", response_model=ApiResponse[ContractorRead])
def get_contractor(    contractor_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": contractor_service.get_contractor(db, contractor_code, current_user)}


@router.post("", response_model=ApiResponse[ContractorRead], status_code=status.HTTP_201_CREATED)
def create_contractor(
    payload: ContractorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": contractor_service.create_contractor(db, payload.model_dump(), current_user)}


@router.put("/{contractor_code}", response_model=ApiResponse[ContractorRead])
def update_contractor(
    contractor_code: str,
    payload: ContractorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": contractor_service.update_contractor(db, contractor_code, payload.model_dump(), current_user)}


@router.delete("/{contractor_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contractor(
    contractor_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    contractor_service.delete_contractor(db, contractor_code, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
