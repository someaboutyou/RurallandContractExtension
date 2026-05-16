from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.cbht import Cbht
from app.models.survey import SurveyCbdkxxBase, SurveyCbdkxxResult
from app.models.user import User
from app.schemas.pagination import PageResponse
from app.schemas.response import ApiResponse
from app.schemas.land_parcel import LandParcelItem
from app.schemas.survey import (
    SurveyBatchCreate,
    SurveyBatchRead,
    SurveyAuthorizationCreate,
    SurveyAuthorizationRevoke,
    SurveyChangeDiffRead,
    SurveyChangeHeadRequest,
    SurveyChangeRecordRead,
    SurveyContractorRead,
    SurveyContractorUpdate,
    SurveyContractRead,
    SurveyMaintainMembersRequest,
    SurveyDeregisterRequest,
    SurveyAddParcelRequest,
    SurveySplitParcelRequest,
    SurveySwapParcelsRequest,
    SurveySplitHouseholdRequest,
    SurveyMergeHouseholdRequest,
    SurveyGenerateRequest,
    SurveyRestructureCreate,
    SurveyTagCreate,
    SurveyTagDisable,
    SurveyTaskSkip,
    SurveyTaskRead,
)
from app.services.contract_template_service import contract_template_service
from app.services.land_parcel_service import land_parcel_service
from app.services.survey_service import survey_service

router = APIRouter()


@router.get("/batches", response_model=ApiResponse[PageResponse[SurveyBatchRead]])
def list_survey_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.list_batches(db, page, page_size, keyword, region_code, current_user)}


@router.post("/batches", response_model=ApiResponse[SurveyBatchRead])
def create_survey_batch(
    payload: SurveyBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.create_batch(db, payload.model_dump(), current_user)}


@router.get("/batches/{batch_id}/tasks", response_model=ApiResponse[PageResponse[SurveyTaskRead]])
def list_survey_tasks(
    batch_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    task_status: str | None = Query(default=None, alias="taskStatus"),
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": survey_service.list_tasks(
            db,
            batch_id=batch_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
            task_status=task_status,
            region_code=region_code,
            current_user=current_user,
        )
    }


@router.get("/batches/{batch_id}/results/{contractor_uid}", response_model=ApiResponse[SurveyContractorRead])
def get_survey_result(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.get_result(db, batch_id, contractor_uid, current_user)}


@router.get("/batches/{batch_id}/results/{contractor_uid}/parcels", response_model=ApiResponse[list[LandParcelItem]])
def get_survey_parcels(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    result = survey_service.get_result(db, batch_id, contractor_uid, current_user)
    cbfbm = result.get("code", "")
    return {"data": land_parcel_service.get_survey_parcels(db, batch_id, cbfbm, current_user)}


@router.get("/batches/{batch_id}/results/{contractor_uid}/phase2", response_model=ApiResponse[dict])
def get_survey_phase2_context(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.get_phase2_context(db, batch_id, contractor_uid, current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/tags/refresh", response_model=ApiResponse[list])
def refresh_survey_tags(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {"data": survey_service.refresh_auto_tags(db, batch_id, contractor_uid, current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/tags", response_model=ApiResponse[dict], status_code=status.HTTP_201_CREATED)
def create_survey_tag(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyTagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.create_manual_tag(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.post("/tags/{tag_id}/disable", response_model=ApiResponse[dict])
def disable_survey_tag(
    tag_id: int,
    payload: SurveyTagDisable,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.disable_tag(db, tag_id, payload.disabledReason, current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/restructures", response_model=ApiResponse[dict], status_code=status.HTTP_201_CREATED)
def create_survey_restructure(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyRestructureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.save_restructure(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.put("/restructures/{restructure_id}", response_model=ApiResponse[dict])
def update_survey_restructure(
    restructure_id: int,
    payload: SurveyRestructureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.update_restructure(db, restructure_id, payload.model_dump(), current_user)}


@router.delete("/restructures/{restructure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_survey_restructure(
    restructure_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    survey_service.delete_restructure(db, restructure_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batches/{batch_id}/results/{contractor_uid}/authorizations", response_model=ApiResponse[dict], status_code=status.HTTP_201_CREATED)
def create_survey_authorization(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyAuthorizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.save_authorization(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.put("/authorizations/{authorization_id}", response_model=ApiResponse[dict])
def update_survey_authorization(
    authorization_id: int,
    payload: SurveyAuthorizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.update_authorization(db, authorization_id, payload.model_dump(), current_user)}


@router.post("/authorizations/{authorization_id}/file", response_model=ApiResponse[dict])
async def upload_survey_authorization_file(
    authorization_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": await survey_service.upload_authorization_file(db, authorization_id, file, current_user)}


@router.get("/authorizations/{authorization_id}/file")
def download_survey_authorization_file(
    authorization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    item = survey_service.get_authorization_file(db, authorization_id, current_user)
    return FileResponse(path=Path(item.storage_path), media_type=item.content_type or "application/octet-stream", filename=item.original_name or "authorization")


@router.get("/authorizations/{authorization_id}/template")
def download_survey_authorization_template(
    authorization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    filename, content = survey_service.build_authorization_template(db, authorization_id, current_user)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/authorizations/{authorization_id}/revoke", response_model=ApiResponse[dict])
def revoke_survey_authorization(
    authorization_id: int,
    payload: SurveyAuthorizationRevoke,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.revoke_authorization(db, authorization_id, payload.revokeReason, current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/attachments", response_model=ApiResponse[dict], status_code=status.HTTP_201_CREATED)
async def upload_survey_attachment(
    batch_id: int,
    contractor_uid: str,
    category: str = Form(...),
    description: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": await survey_service.upload_attachment(db, batch_id, contractor_uid, category, description, file, current_user)}


@router.get("/attachments/{attachment_id}/download")
def download_survey_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    item = survey_service.get_attachment(db, attachment_id, current_user)
    return FileResponse(path=Path(item.storage_path), media_type=item.content_type or "application/octet-stream", filename=item.original_name)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_survey_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    survey_service.delete_attachment(db, attachment_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batches/{batch_id}/results/{contractor_uid}/generate-request", response_model=ApiResponse[dict])
def generate_request_from_survey_result(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requests.manage")),
):
    return {"data": survey_service.generate_request_from_result(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.get("/batches/{batch_id}/changes", response_model=ApiResponse[PageResponse[SurveyChangeRecordRead]])
def list_survey_changes(
    batch_id: int,
    contractor_uid: str | None = Query(default=None, alias="contractorUid"),
    region_code: str | None = Query(default=None, alias="regionCode"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": survey_service.list_changes(
            db,
            batch_id=batch_id,
            contractor_uid=contractor_uid,
            region_code=region_code,
            page=page,
            page_size=page_size,
            current_user=current_user,
        )
    }


@router.get("/batches/{batch_id}/export-results.zip")
def export_survey_results(
    batch_id: int,
    region_code: str | None = Query(default=None, alias="regionCode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    filename, content = survey_service.build_results_zip(db, batch_id, current_user, region_code)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/batches/{batch_id}/results/{contractor_uid}/diffs", response_model=ApiResponse[PageResponse[SurveyChangeDiffRead]])
def list_survey_diffs(
    batch_id: int,
    contractor_uid: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    return {
        "data": survey_service.list_diffs(
            db,
            batch_id=batch_id,
            contractor_uid=contractor_uid,
            page=page,
            page_size=page_size,
            current_user=current_user,
        )
    }


@router.put("/batches/{batch_id}/results/{contractor_uid}", response_model=ApiResponse[SurveyContractorRead])
def update_survey_result(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyContractorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.update_result(db, batch_id, contractor_uid, payload.model_dump(), current_user)}


@router.post("/batches/{batch_id}/results/{contractor_uid}/confirm", response_model=ApiResponse[SurveyContractorRead])
def confirm_survey_result(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.confirm_result(db, batch_id, contractor_uid, current_user)}


@router.post("/batches/{batch_id}/tasks/{contractor_uid}/skip", response_model=ApiResponse[SurveyTaskRead])
def skip_survey_task(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyTaskSkip,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.skip_task(db, batch_id, contractor_uid, payload.skipReason, current_user)}


# ── 合同信息 ──────────────────────────────────────────

def _get_cbhtbm_for_contractor(db: Session, cbfbm: str, batch_id: int) -> str | None:
    """查找承包方关联的合同编码，优先 result 表再 fallback base 表。"""
    cbhtbm = db.scalar(
        sa_select(SurveyCbdkxxResult.cbhtbm)
        .where(SurveyCbdkxxResult.cbfbm == cbfbm)
        .where(SurveyCbdkxxResult.batch_id == batch_id)
        .limit(1)
    )
    if not cbhtbm:
        cbhtbm = db.scalar(
            sa_select(SurveyCbdkxxBase.cbhtbm)
            .where(SurveyCbdkxxBase.cbfbm == cbfbm)
            .limit(1)
        )
    return cbhtbm


@router.get("/batches/{batch_id}/results/{contractor_uid}/contract", response_model=ApiResponse[SurveyContractRead])
def get_survey_contract(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """获取承包方的合同信息及渲染后的 HTML 合同。"""
    result = survey_service.get_result(db, batch_id, contractor_uid, current_user)
    cbfbm = result.get("code", "")
    cbhtbm = _get_cbhtbm_for_contractor(db, cbfbm, batch_id)
    if not cbhtbm:
        return {"data": None}

    contract = db.scalar(sa_select(Cbht).where(Cbht.cbhtbm == cbhtbm))
    if not contract:
        return {"data": None}

    rendered = contract_template_service.render_contract(
        db, cbhtbm=cbhtbm, batch_id=batch_id,
    )
    return {
        "data": {
            "cbhtbm": contract.cbhtbm,
            "ycbhtbm": contract.ycbhtbm,
            "fbfbm": contract.fbfbm,
            "fbfmc": None,
            "cbfbm": contract.cbfbm,
            "cbfs": contract.cbfs,
            "cbqxq": str(contract.cbqxq) if contract.cbqxq else None,
            "cbqxz": str(contract.cbqxz) if contract.cbqxz else None,
            "htzmj": float(contract.htzmj) if contract.htzmj else None,
            "htzmjm": float(contract.htzmjm) if contract.htzmjm else None,
            "cbdkzs": contract.cbdkzs,
            "qdsj": str(contract.qdsj) if contract.qdsj else None,
            "renderedHtml": rendered,
        }
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/contract/print")
def print_survey_contract(
    batch_id: int,
    contractor_uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.view")),
):
    """返回合同 HTML 用于打印。"""
    result = survey_service.get_result(db, batch_id, contractor_uid, current_user)
    cbfbm = result.get("code", "")
    cbhtbm = _get_cbhtbm_for_contractor(db, cbfbm, batch_id)
    if not cbhtbm:
        return Response(content="", media_type="text/html")
    rendered = contract_template_service.render_contract(
        db, cbhtbm=cbhtbm, batch_id=batch_id,
    )
    return Response(content=rendered, media_type="text/html; charset=utf-8")


# ── 调查操作 ──────────────────────────────────────────

@router.post("/batches/{batch_id}/results/{contractor_uid}/change-head", response_model=ApiResponse[SurveyContractorRead])
def change_household_head(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyChangeHeadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """更换户主。"""
    return {
        "data": survey_service.change_household_head(
            db, batch_id, contractor_uid,
            payload.newHeadMemberUid, payload.reason, current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/maintain-members", response_model=ApiResponse[SurveyContractorRead])
def maintain_survey_members(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyMaintainMembersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """家庭成员维护：批量增删改。"""
    return {
        "data": survey_service.maintain_members(
            db, batch_id, contractor_uid,
            [m.model_dump() for m in payload.membersToAdd],
            [m.model_dump() for m in payload.membersToUpdate],
            payload.membersToDelete, payload.reason, current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/deregister", response_model=ApiResponse[dict])
def deregister_contractor(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyDeregisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """注销承包方：物理删除 result，base 保留，before_summary 存完整快照。"""
    return {
        "data": survey_service.deregister_contractor(
            db, batch_id, contractor_uid, payload.reason, current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/add-parcel", response_model=ApiResponse[dict])
def add_parcel(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyAddParcelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """新增地块：创建 SurveyDkResult + SurveyCbdkxxResult。"""
    return {
        "data": survey_service.add_parcel(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/split-parcel", response_model=ApiResponse[dict])
def split_survey_parcel(
    batch_id: int,
    contractor_uid: str,
    payload: SurveySplitParcelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """切割地块：减小原地块面积，创建新地块。"""
    return {
        "data": survey_service.split_parcel(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/swap-parcels", response_model=ApiResponse[dict])
def swap_survey_parcels(
    batch_id: int,
    contractor_uid: str,
    payload: SurveySwapParcelsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """地块互换：交换两个承包方的地块归属。"""
    return {
        "data": survey_service.swap_parcels(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/split-household", response_model=ApiResponse[dict])
def split_household(
    batch_id: int,
    contractor_uid: str,
    payload: SurveySplitHouseholdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """分户：创建新承包方，迁移指定成员和地块。"""
    return {
        "data": survey_service.split_household(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/results/{contractor_uid}/merge-household", response_model=ApiResponse[dict])
def merge_household(
    batch_id: int,
    contractor_uid: str,
    payload: SurveyMergeHouseholdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    """合户：将源承包方全部成员和地块迁移到目标承包方，注销源承包方。"""
    return {
        "data": survey_service.merge_household(
            db, batch_id, contractor_uid, payload.model_dump(), current_user,
        )
    }


@router.post("/batches/{batch_id}/finish", response_model=ApiResponse[SurveyBatchRead])
def finish_survey_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contractors.manage")),
):
    return {"data": survey_service.finish_batch(db, batch_id, current_user)}
